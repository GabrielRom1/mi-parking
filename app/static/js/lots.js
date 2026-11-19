// Lot Management (admin): list loading, existing-lot editing, and notifications.
(() => {
	const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
	const $ = (selector, root = document) => root.querySelector(selector);
	const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

	const table = $('[data-lots-table]');
	const tbody = $('[data-lots-body]');
	const skeletonHtml = tbody.innerHTML;
	const listStatus = $('[data-lots-status]');
	const countLabel = $('[data-lots-count]');
	const toastLayer = $('[data-toasts]');
	const searchInput = $('[data-lot-search]');
	const filterButtons = $$('[data-lot-filter]');
	const dialog = $('[data-edit-dialog]');
	const actionDialog = $('[data-action-dialog]');
	const form = $('[data-edit-form]');
	const floorList = $('[data-floor-list]');
	const floorPanels = $('[data-floor-panels]');
	const submitButton = $('[data-submit]');
	let floors = [];
	let selected = -1;
	let editingUrl = null;
	let dialogMode = 'create';
	let submitting = false;
	let lotFilter = 'all';
	let pendingAction = null;
	let floorDeletionDecisions = {};
	const submitLabel = () => (
		floors.length ? 'Crear lote' : 'Crear lote vacío'
	);

	function bringToastsToFront() {
		if (!toastLayer.showPopover) return;
		toastLayer.toggleAttribute('data-over-dialog', dialog.open);
		if (toastLayer.matches(':popover-open')) toastLayer.hidePopover();
		toastLayer.showPopover();
	}

	function dismissToast(toast) {
		if (!toast.isConnected || toast.dataset.closing !== undefined) return;
		const remove = () => {
			toast.remove();
			if (!toastLayer.childElementCount && toastLayer.hidePopover) toastLayer.hidePopover();
		};
		if (reduceMotion.matches) {
			remove();
			return;
		}
		toast.dataset.closing = '';
		toast.addEventListener('animationend', remove, { once: true });
		setTimeout(remove, 400);
	}

	function showToast({ tone = 'success', title, message }) {
		const toast = $('#toast-template').content.firstElementChild.cloneNode(true);
		toast.dataset.tone = tone;
		toast.setAttribute('role', tone === 'error' ? 'alert' : 'status');
		$('[data-toast-title]', toast).textContent = title;
		$('[data-toast-message]', toast).textContent = message;
		$('[data-toast-close]', toast).addEventListener('click', () => dismissToast(toast));
		toastLayer.replaceChildren(toast);
		bringToastsToFront();
		setTimeout(() => dismissToast(toast), tone === 'error' ? 8000 : 5000);
	}

	function followLoginRedirect(response) {
		if (response.redirected) window.location.assign(response.url);
		return response.redirected;
	}


	// these 2 functions implement the filters from the client side.
	// In the future if you want we can move the search to the backend if we decide to paginate
	function normalizeSearch(value) {
		return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
	}

	function updateCount() {
		const rows = $$('tr[data-lot-id]', tbody);
		const total = rows.length;
		const active = rows.filter((row) => row.dataset.active === 'true').length;
		const inactive = total - active;
		const search = normalizeSearch(searchInput.value.trim());
		let visible = 0;

		$('[data-filter-count="all"]').textContent = `· ${total}`;
		$('[data-filter-count="active"]').textContent = `· ${active}`;
		$('[data-filter-count="inactive"]').textContent = `· ${inactive}`;
		rows.forEach((row) => {
			const matchesFilter = lotFilter === 'all'
				|| row.dataset.active === String(lotFilter === 'active');
			const matchesSearch = !search
				|| normalizeSearch(row.dataset.search).includes(search);
			row.hidden = !(matchesFilter && matchesSearch);
			if (!row.hidden) visible += 1;

			const date = row.dataset.deletionDate;
			const dateLabel = $('[data-deletion-date-label]', row);
			if (date) {
				const [scheduledDay, scheduledTime = ''] = date.split('T');
				dateLabel.dateTime = date;
				const formattedDay = new Intl.DateTimeFormat('es', {
					day: 'numeric',
					month: 'short',
				}).format(new Date(`${scheduledDay}T00:00:00`));
				dateLabel.textContent =
					`Elimina ${formattedDay}${scheduledTime ? ` · ${scheduledTime.slice(0, 5)}` : ''}`;
				dateLabel.hidden = false;
			} else {
				dateLabel.hidden = true;
			}
			const deactivationDate = row.dataset.deactivationDate;
			const deactivationLabel = $('[data-deactivation-date-label]', row);
			if (deactivationDate) {
				deactivationLabel.dateTime = deactivationDate;
				const [scheduledDay, scheduledTime = ''] = deactivationDate.split('T');
				deactivationLabel.textContent = `Desactiva ${new Intl.DateTimeFormat('es', {
					day: 'numeric',
					month: 'short',
				}).format(new Date(`${scheduledDay}T00:00:00`))}${scheduledTime
					? ` · ${scheduledTime.slice(0, 5)}`
					: ''}`;
				deactivationLabel.hidden = false;
			} else {
				deactivationLabel.hidden = true;
			}
		});

		$('[data-filter-empty]', tbody)?.remove();
		if (total && !visible) {
			tbody.append($('#lots-filter-empty-template').content.firstElementChild.cloneNode(true));
		}
		countLabel.hidden = total === 0;
		countLabel.textContent = `Mostrando ${visible} de ${total} ${total === 1 ? 'lote' : 'lotes'}.`;
	}

	function setListState(state) {
		table.setAttribute('aria-busy', String(state === 'loading'));
		listStatus.textContent = {
			loading: 'Cargando lotes…',
			error: 'No se pudieron cargar los lotes.',
			ready: '',
		}[state];
	}

	async function loadRows() {
		tbody.innerHTML = skeletonHtml;
		setListState('loading');
		countLabel.hidden = true;
		try {
			const response = await fetch(table.dataset.rowsUrl, {
				headers: { Accept: 'text/html' },
			});
			if (followLoginRedirect(response)) return;
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			tbody.innerHTML = await response.text();
			setListState('ready');
			updateCount();
		} catch {
			tbody.replaceChildren($('#lots-error-template').content.cloneNode(true));
			$('[data-retry]', tbody).addEventListener('click', loadRows);
			setListState('error');
		}
	}

	function insertRow(rowHtml) {
		const holder = document.createElement('tbody');
		holder.innerHTML = rowHtml.trim();
		const row = holder.firstElementChild;
		const listIsShowing = !$('[data-skeleton], [data-error-state]', tbody);
		if (!listIsShowing) {
			loadRows();
			return;
		}

		$('[data-empty-state]', tbody)?.remove();
		const next = $$('tr[data-lot-id]', tbody)
			.find((other) => other.dataset.sortKey > row.dataset.sortKey);
		tbody.insertBefore(row, next ?? null);
		updateCount();
		row.scrollIntoView({
			block: 'nearest',
			behavior: reduceMotion.matches ? 'auto' : 'smooth',
		});
		row.dataset.new = '';
		setTimeout(() => delete row.dataset.new, 2400);
	}

	function fromTemplate(id, index) {
		const html = $(id).innerHTML
			.replaceAll('__i__', index)
			.replaceAll('__n__', index + 1);
		const holder = document.createElement('template');
		holder.innerHTML = html.trim();
		return holder.content.firstElementChild;
	}

	function fieldParts(input) {
		const field = input.closest('[data-field]');
		return { help: $('[data-help]', field), error: $('[data-error]', field) };
	}

	function setFieldError(input, message) {
		const { help, error } = fieldParts(input);
		if (!message) {
			input.removeAttribute('aria-invalid');
			error.hidden = true;
			if (help) help.hidden = false;
			return;
		}
		input.setAttribute('aria-invalid', 'true');
		$('[data-error-text]', error).textContent = message;
		error.hidden = false;
		if (help) help.hidden = true;
	}

	function clearAllErrors() {
		$$('[aria-invalid]', form).forEach((input) => setFieldError(input, ''));
	}

	const numberValue = (input) => (
		input.value.trim() === '' ? null : Number(input.value)
	);
	const pluralize = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
	const spotsSummary = (spots, accessible) => (
		`${pluralize(spots, 'espacio')} · ${pluralize(accessible, 'accesible')}`
	);

	function refreshFloorItem({ item, panel }, index) {
		const selectButton = $('[data-floor-select]', item);
		const isSelected = index === selected;
		panel.hidden = !isSelected;
		selectButton.setAttribute('aria-current', String(isSelected));
		const floor = floors[index];
		floor.canRemove = index === floors.length - 1;
		const removeButton = $('[data-remove-floor]', item);
		removeButton.hidden = !floor.canRemove && floor.id === null;
		removeButton.setAttribute(
			'aria-label',
			floor.canRemove ? `Administrar o eliminar piso ${index + 1}` : `Administrar piso ${index + 1}`,
		);

		if ($('[aria-invalid]', panel)) {
			selectButton.dataset.invalid = '';
			$('[data-floor-summary]', item).textContent = 'Necesita atención';
			return;
		}
		delete selectButton.dataset.invalid;
		const capacity = numberValue($('[data-capacity]', panel));
		const accessible = numberValue($('[data-accessible]', panel));
		$('[data-floor-summary]', item).textContent = capacity === null
			? 'Sin configurar'
			: spotsSummary(capacity, accessible ?? 0);
		refreshFloorSchedule(floor);
	}

	function refreshFloorSchedule(floor) {
		const label = $('[data-floor-schedule]', floor.item);
		if (floor.dateToBeDeleted) {
			label.textContent = `Eliminación programada: ${floor.dateToBeDeleted.replace('T', ' ').slice(0, 16)}`;
			label.hidden = false;
		} else if (floor.dateToBeDeactivated) {
			label.textContent = `Desactivación programada: ${floor.dateToBeDeactivated.replace('T', ' ').slice(0, 16)}`;
			label.hidden = false;
		} else if (!floor.isActive) {
			label.textContent = 'Inactivo';
			label.hidden = false;
		} else {
			label.hidden = true;
		}
	}

	function refreshFloors() {
		const hasFloors = floors.length > 0;
		$('[data-floor-count]').textContent = floors.length;
		$('[data-no-floors]').hidden = hasFloors;
		$('[data-no-floor-fields]').hidden = hasFloors;
		$('[data-floor-heading]').textContent = selected >= 0
			? `Campos por piso · Piso ${selected + 1}`
			: 'Campos por piso';
		const capacity = floors.reduce(
			(total, floor) => total + (numberValue($('[data-capacity]', floor.panel)) || 0),
			0,
		);
		const accessible = floors.reduce(
			(total, floor) => total + (numberValue($('[data-accessible]', floor.panel)) || 0),
			0,
		);
		$('[data-lot-total]').textContent = spotsSummary(capacity, accessible);
		floors.forEach(refreshFloorItem);
	}

	function selectFloor(index) {
		selected = index;
		refreshFloors();
	}

	function checkAccessibleCapacity(panel) {
		const capacityInput = $('[data-capacity]', panel);
		const accessibleInput = $('[data-accessible]', panel);
		const capacity = numberValue(capacityInput);
		const accessible = numberValue(accessibleInput);
		if (capacity !== null && accessible !== null && accessible > capacity) {
			setFieldError(accessibleInput, `No puede exceder la capacidad del piso (${capacity}).`);
		} else if (accessible !== null && accessibleInput.getAttribute('aria-invalid')) {
			setFieldError(accessibleInput, '');
		}
	}

	function addFloor(floorData = null) {
		const index = floors.length;
		const item = fromTemplate('#floor-item-template', index);
		const panel = fromTemplate('#floor-panel-template', index);
		const floor = {
			id: floorData?.id ?? null,
			item,
			panel,
			isActive: floorData?.is_active ?? true,
			dateToBeDeleted: floorData?.date_to_be_deleted ?? null,
			dateToBeDeactivated: floorData?.date_to_be_deactivated ?? null,
		};
		$('[data-floor-select]', item).addEventListener('click', () => {
			selectFloor(floors.indexOf(floor));
		});
		$('[data-remove-floor]', item).addEventListener('click', () => {
			void requestFloorRemoval(floor);
		});
		$('[data-capacity]', panel).value = floorData?.capacity ?? '';
		$('[data-accessible]', panel).value = floorData?.accessible_capacity ?? '';
		$('[name$="-role_id"]', panel).value = floorData?.role_id ?? '';
		floorList.prepend(item);
		floorPanels.append(panel);
		floors.push(floor);
		selectFloor(index);
	}

	function removeFloorFromEditor(floor) {
		const index = floors.indexOf(floor);
		if (index < 0) return;
		const selectedFloor = floors[selected];
		floors.splice(index, 1);
		floor.item.remove();
		floor.panel.remove();
		selectFloor(
			selectedFloor === floor
				? Math.min(index, floors.length - 1)
				: floors.indexOf(selectedFloor),
		);
		$('[data-add-floor]').focus();
	}

	async function requestFloorRemoval(floor) {
		if (!floor) return;
		if (floor.id === null) {
			removeFloorFromEditor(floor);
			return;
		}

		const removeButton = $('[data-remove-floor]', floor.item);
		removeButton.disabled = true;
		try {
			const clickedAtMs = Date.now();
			const previewUrl = new URL(editingUrl, window.location.origin);
			previewUrl.pathname = previewUrl.pathname.replace(
				/\/\d+$/,
				`/${floor.id}/delete/preview`,
			);
			const response = await fetch(previewUrl, {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({ clicked_at_ms: clickedAtMs }),
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (!response.ok) {
				throw new Error(data.message || 'No se pudo verificar el piso.');
			}
			askForFloorDeletion(
				{ ...data, floor_id: floor.id },
				floor,
				false,
			);
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo verificar el piso',
				message: error.message || 'Inténtalo de nuevo.',
			});
		} finally {
			removeButton.disabled = false;
		}
	}

	function resetForm() {
		form.reset();
		$('#name', form).readOnly = false;
		floorDeletionDecisions = {};
		floors.forEach(({ item, panel }) => {
			item.remove();
			panel.remove();
		});
		floors = [];
		selected = -1;
		editingUrl = null;
		submitButton.disabled = false;
		submitButton.setAttribute('aria-busy', 'false');
		$('[data-submit-idle]', submitButton).hidden = false;
		$('[data-submit-busy]', submitButton).hidden = true;
		$('[data-submit-label]', submitButton).textContent = submitLabel();
		clearAllErrors();
		refreshFloors();
	}

	function showServerErrors(errors) {
		for (const [name, message] of Object.entries(errors)) {
			const input = form.elements.namedItem(name);
			if (input && input.type !== 'hidden') setFieldError(input, message);
		}
		const invalidLotField = $('#name[aria-invalid], #location[aria-invalid]', form);
		const invalidFloorField = $('[aria-invalid]', floorPanels);
		if (!invalidLotField && invalidFloorField) {
			selected = floors.findIndex(({ panel }) => panel.contains(invalidFloorField));
			refreshFloors();
		}
		(invalidLotField ?? invalidFloorField)?.focus();
	}

	async function openEditor(url) {
		resetForm();
		dialogMode = 'edit';
		$('#create-lot-title').textContent = 'Editar lote';
		$('#create-lot-desc').textContent =
			'Los campos generales aplican a todo el lote. Selecciona un piso a la izquierda para definir su capacidad y rol.';
		$('[data-no-floors]').textContent = 'Este lote todavía no tiene pisos.';
		$('[data-no-floor-fields]').textContent =
			'Agrega un piso para definir su capacidad, espacios accesibles y rol.';
		$('[data-submit-label]').textContent = 'Guardar cambios';
		try {
			const response = await fetch(url, { headers: { Accept: 'application/json' } });
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (!response.ok) throw new Error(data.message || 'No se pudo cargar el lote.');

			editingUrl = url;
			$('#name', form).value = data.lot.name;
			$('#name', form).readOnly = true;
			$('#location', form).value = data.lot.location;
			$('[name="is_paid"]', form).checked = data.lot.is_paid;
			data.lot.floors.forEach((floor) => addFloor(floor));
			if (!floors.length) refreshFloors();
			dialog.showModal();
			$('#name', form).focus();
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo abrir el lote',
				message: error.message || 'Inténtalo de nuevo.',
			});
		}
	}

	function setSubmitting(value) {
		submitting = value;
		submitButton.disabled = value;
		submitButton.setAttribute('aria-busy', String(value));
		$('[data-submit-idle]', submitButton).hidden = value;
		$('[data-submit-busy]', submitButton).hidden = !value;
		$('[data-submit-label]', submitButton).textContent = value
			? (dialogMode === 'create' ? 'Creando…' : 'Guardando…')
			: (dialogMode === 'create' ? submitLabel() : 'Guardar cambios');
	}

	function validateForm() {
		const requiredFields = [
			[$('#name', form), 'Introduce el nombre del lote.'],
			[$('#location', form), 'Introduce la ubicación.'],
		];
		for (const [input, message] of requiredFields) {
			if (!input.value.trim()) {
				setFieldError(input, message);
				input.focus();
				return false;
			}
		}

		for (const [index, floor] of floors.entries()) {
			const capacityInput = $('[data-capacity]', floor.panel);
			const accessibleInput = $('[data-accessible]', floor.panel);
			const capacity = numberValue(capacityInput);
			const accessible = numberValue(accessibleInput);
			let invalidInput = null;
			let message = '';

			if (capacity === null || !Number.isInteger(capacity) || capacity < 0) {
				invalidInput = capacityInput;
				message = 'Introduce una capacidad entera igual o mayor que cero.';
			} else if (
				accessible === null
				|| !Number.isInteger(accessible)
				|| accessible < 0
			) {
				invalidInput = accessibleInput;
				message = 'Introduce una capacidad accesible entera igual o mayor que cero.';
			} else if (accessible > capacity) {
				invalidInput = accessibleInput;
				message = `No puede exceder la capacidad del piso (${capacity}).`;
			}

			if (invalidInput) {
				setFieldError(invalidInput, message);
				selectFloor(index);
				invalidInput.focus();
				return false;
			}
		}
		return true;
	}

	async function submit(event) {
		event.preventDefault();
		if (submitting || (dialogMode === 'edit' && !editingUrl)) return;
		clearAllErrors();
		if (!validateForm()) return;

		setSubmitting(true);
		try {
			const response = dialogMode === 'create'
				? await fetch(form.action, {
					method: 'POST',
					body: new FormData(form),
					headers: { Accept: 'application/json' },
				})
				: await fetch(editingUrl, {
					method: 'PUT',
					headers: {
						Accept: 'application/json',
						'Content-Type': 'application/json',
					},
					body: JSON.stringify({
						name: $('#name', form).value.trim(),
						location: $('#location', form).value.trim(),
						is_paid: $('[name="is_paid"]', form).checked,
						floor_deletion_decisions: floorDeletionDecisions,
						floors: floors.map(({ id, panel }) => ({
							id,
							capacity: numberValue($('[data-capacity]', panel)),
							accessible_capacity: numberValue($('[data-accessible]', panel)),
							role_id: $('[name$="-role_id"]', panel).value
								? Number($('[name$="-role_id"]', panel).value)
								: null,
						})),
					}),
				});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (response.status === 409 && data.floor_deletions?.length) {
				askForFloorDeletion(data.floor_deletions[0], null, true);
				return;
			}
			if (!response.ok) {
				if (data.errors) showServerErrors(data.errors);
				throw new Error(data.message || 'Corrige los datos e inténtalo de nuevo.');
			}

			dialog.close();
			if (dialogMode === 'create') {
				resetForm();
				insertRow(data.row_html);
				showToast({ title: 'Lote creado', message: data.message });
			} else {
				await loadRows();
				showToast({
					title: data.scheduled_floor_ids?.length
						? 'Eliminación de piso programada'
						: 'Lote actualizado',
					message: data.message,
				});
			}
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo guardar el lote',
				message: error.message || 'Revisa tu conexión e inténtalo de nuevo.',
			});
		} finally {
			setSubmitting(false);
		}
	}

	tbody.addEventListener('click', (event) => {
		const target = event.target;
		if (!(target instanceof Element)) return;
		const button = target.closest('[data-edit-lot]');
		if (button) openEditor(button.dataset.editUrl);
	});

	function askForLotAction({
		button,
		url,
		kind,
		message,
		lotName = null,
		minimumDate,
		minimumToken = null,
		windowEnd = null,
		windowHours = null,
		slotMinutes = null,
		canSchedule = true,
		scheduledAt = null,
		scheduledAction = null,
		hasPendingReservations = false,
	}) {
		pendingAction = {
			button,
			url,
			kind,
			minimumToken,
			scheduledAt: kind === 'delete' ? minimumDate : null,
			windowEnd,
			windowHours,
			slotMinutes,
			canSchedule,
			scheduledAction,
			hasPendingReservations,
		};
		$('#action-dialog-title').textContent = kind === 'delete'
			? `¿Cómo deseas eliminar ${lotName ? `«${lotName}»` : 'este lote'}?`
			: `¿Cómo deseas desactivar ${lotName ? `«${lotName}»` : 'este lote'}?`;
		$('#action-dialog-desc').textContent = kind === 'delete'
			? `${message} La fecha queda fijada por el sistema; no se puede escoger otra. El override lo elimina ahora y cancela las reservaciones que correspondan.`
			: `${message} Puedes programar la desactivación para una fecha y hora o desactivarlo ahora.`;
		$('[data-action-date-field]', actionDialog).hidden =
			kind !== 'delete' && !scheduledAt;
		$('[data-action-date-picker-field]', actionDialog).hidden = kind === 'delete'
			|| Boolean(scheduledAt);
		$('[data-schedule-deactivation-action]', actionDialog).hidden = true;
		$('[data-cancel-schedule-action]', actionDialog).hidden = !scheduledAction;
		$('[data-override-action]', actionDialog).hidden = Boolean(scheduledAction);
		$('[data-schedule-action]', actionDialog).hidden =
			!canSchedule || Boolean(scheduledAction);
		$('[data-schedule-action]', actionDialog).textContent =
			kind === 'delete' ? 'Programar eliminación' : 'Programar desactivación';
		const dateInput = $('[data-action-date]', actionDialog);
		dateInput.type = kind === 'delete' ? 'date' : 'datetime-local';
		dateInput.step = kind === 'delete' ? '1' : '60';
		dateInput.min = kind === 'delete'
			? minimumDate.slice(0, 10)
			: minimumDate;
		dateInput.value = kind === 'delete'
			? minimumDate.slice(0, 10)
			: minimumDate;
		$('[data-action-date-hint]', actionDialog).textContent =
			`La fecha y hora mínima es ${minimumDate}.`;
		$('[data-action-datetime-display]', actionDialog).textContent =
			kind === 'delete'
				? minimumDate.replace('T', ' ')
				: scheduledAt
					? scheduledAt.replace('T', ' ')
					: '';
		$('[data-action-date-field] > span:first-child', actionDialog).textContent =
			kind === 'delete' ? 'Eliminación programada' : 'Desactivación programada';
		$('[data-deletion-date-hint]', actionDialog).textContent = canSchedule
			? kind === 'delete'
				? `Programada automáticamente para ${windowHours} horas y ${slotMinutes} minutos después de abrir este diálogo.`
				: 'Al llegar la fecha y hora, el scheduler marcará el lote y sus pisos como inactivos.'
			: 'No se puede programar mientras el lote tenga una eliminación programada; cancélala primero.';
		$('[data-override-action]', actionDialog).textContent =
			kind === 'delete'
				? 'Eliminar ahora con override'
				: pendingAction.hasPendingReservations
					? 'Desactivar ahora con override'
					: 'Desactivar ahora';
		actionDialog.showModal();
		$('[data-schedule-action]', actionDialog).hidden
			? $('[data-override-action]', actionDialog).focus()
			: $('[data-schedule-action]', actionDialog).focus();
	}

	function askForDeleteConfirmation(button) {
		pendingAction = {
			button,
			url: button.dataset.deleteUrl,
			kind: 'delete-confirm',
		};
		$('#action-dialog-title').textContent = '¿Eliminar este lote?';
		$('#action-dialog-desc').textContent =
			'Esta acción eliminará el lote, sus pisos y sus espacios. No se encontraron reservaciones pendientes.';
		$('[data-action-date-field]', actionDialog).hidden = true;
		$('[data-action-date-picker-field]', actionDialog).hidden = true;
		$('[data-schedule-action]', actionDialog).hidden = true;
		$('[data-schedule-deactivation-action]', actionDialog).hidden = true;
		$('[data-cancel-schedule-action]', actionDialog).hidden = true;
		$('[data-override-action]', actionDialog).hidden = false;
		$('[data-override-action]', actionDialog).textContent = 'Eliminar lote';
		actionDialog.showModal();
		$('[data-override-action]', actionDialog).focus();
	}

	function askForFloorDeletion(issue, floor = null, submitAfterDecision = false) {
		const hasPending = issue.has_pending_reservations;
		const hasScheduledDeletion = Boolean(issue.date_to_be_deleted);
		const hasScheduledDeactivation = Boolean(issue.date_to_be_deactivated);
		pendingAction = {
			kind: hasPending ? 'floor-delete' : 'floor-confirm',
			floorId: issue.floor_id,
			floor,
			submitAfterDecision,
			minimumToken: issue.minimum_token,
			scheduledAt: issue.minimum_datetime,
			windowEnd: issue.window_end,
			windowHours: issue.window_hours,
			slotMinutes: issue.slot_minutes,
			canSchedule: issue.can_schedule,
			canRemove: floor?.canRemove ?? false,
			scheduledAction: hasScheduledDeletion
				&& !issue.date_to_be_deleted_inherited
				? 'delete'
				: hasScheduledDeactivation
					&& !issue.date_to_be_deactivated_inherited
					? 'deactivate'
					: null,
		};
		const inheritedSchedule = issue.date_to_be_deleted_inherited
			|| issue.date_to_be_deactivated_inherited;
		$('#action-dialog-title').textContent = 'Administrar piso';
		$('#action-dialog-desc').textContent = inheritedSchedule
			? 'Esta programación pertenece al lote padre; cancélala desde la fila del lote en la lista.'
			: floor && !floor.canRemove
			? 'Desde aquí puedes programar la desactivación o cancelar una acción programada para este piso.'
			: hasPending
				? 'El piso tiene reservaciones pendientes. Puedes programar su eliminación, programar su desactivación o eliminarlo ahora con override.'
				: 'Puedes eliminar el piso ahora o programar su desactivación. Las acciones programadas se pueden cancelar desde aquí.';
		$('[data-action-date-field]', actionDialog).hidden =
			!hasPending && !hasScheduledDeletion && !hasScheduledDeactivation;
		$('[data-action-date-picker-field]', actionDialog).hidden =
			!floor || hasScheduledDeactivation || inheritedSchedule;
		$('[data-schedule-action]', actionDialog).hidden =
			!hasPending || !issue.can_schedule || hasScheduledDeletion
				|| (floor !== null && !floor?.canRemove);
		$('[data-schedule-action]', actionDialog).textContent = 'Programar eliminación';
		$('[data-schedule-deactivation-action]', actionDialog).hidden =
			!floor
			|| hasScheduledDeactivation
			|| issue.date_to_be_deleted_inherited
			|| issue.date_to_be_deactivated_inherited;
		$('[data-cancel-schedule-action]', actionDialog).hidden =
			!floor || !pendingAction.scheduledAction;
		const dateInput = $('[data-action-date]', actionDialog);
		const minimumDeactivationDate = issue.minimum_deactivation_datetime;
		dateInput.type = 'datetime-local';
		dateInput.step = '60';
		dateInput.min = minimumDeactivationDate;
		dateInput.value = minimumDeactivationDate;
		$('[data-action-date-hint]', actionDialog).textContent =
			`La desactivación no puede ser antes del ${minimumDeactivationDate}.`;
		$('[data-override-action]', actionDialog).textContent = hasPending
			? 'Eliminar ahora con override'
			: 'Eliminar piso';
		$('[data-override-action]', actionDialog).hidden =
			Boolean(floor && !floor.canRemove);
		if (hasPending || hasScheduledDeletion) {
			$('[data-action-datetime-display]', actionDialog).textContent =
				hasScheduledDeletion
					? issue.date_to_be_deleted.replace('T', ' ').slice(0, 16)
					: issue.minimum_datetime.replace('T', ' ');
			$('[data-action-date-field] > span:first-child', actionDialog).textContent =
				'Eliminación programada';
			$('[data-deletion-date-hint]', actionDialog).textContent =
				hasScheduledDeletion
					? 'Esta eliminación está programada. Puedes cancelarla o cambiarla por una desactivación programada.'
					: issue.can_schedule
						? `La fecha se fija automáticamente a ${issue.window_hours} horas más un intervalo de ${issue.slot_minutes} minutos desde este clic.`
						: 'No se puede programar la eliminación antes de que terminen las reservaciones; usa override para eliminar ahora.';
		} else if (hasScheduledDeactivation) {
			$('[data-action-datetime-display]', actionDialog).textContent =
				issue.date_to_be_deactivated.replace('T', ' ').slice(0, 16);
			$('[data-action-date-field] > span:first-child', actionDialog).textContent =
				'Desactivación programada';
			$('[data-deletion-date-hint]', actionDialog).textContent =
				'El scheduler marcará el piso inactivo cuando llegue esta fecha y hora.';
		}
		if (!floor) {
			$('[data-schedule-deactivation-action]', actionDialog).hidden = true;
			$('[data-cancel-schedule-action]', actionDialog).hidden = true;
			$('[data-action-date-picker-field]', actionDialog).hidden = true;
		}
		actionDialog.showModal();
		$('[data-override-action]', actionDialog).focus();
	}

	async function prepareParentDeactivation(button) {
		button.disabled = true;
		try {
			const response = await fetch(button.dataset.deletePreviewUrl, {
				method: 'POST',
				headers: { Accept: 'application/json' },
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (!response.ok) {
				throw new Error(data.message || 'No se pudo verificar el lote.');
			}
			askForLotAction({
				button,
				url: button.dataset.toggleUrl,
				kind: 'deactivate',
				lotName: button.closest('[data-lot-name]')?.dataset.lotName,
				message: data.date_to_be_deleted
					? 'Este lote tiene una eliminación programada; puedes reemplazarla por una desactivación programada.'
					: data.has_pending_reservations
						? 'El lote o sus pisos tienen reservaciones pendientes.'
						: 'El lote y sus pisos no tienen reservaciones pendientes.',
				minimumDate: data.minimum_deactivation_datetime,
				canSchedule: true,
				scheduledAt: data.date_to_be_deactivated,
				scheduledAction: data.date_to_be_deactivated ? 'deactivate' : null,
				hasPendingReservations: data.has_pending_reservations,
			});
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo verificar el lote',
				message: error.message || 'Inténtalo de nuevo.',
			});
		} finally {
			button.disabled = false;
		}
	}

	function isDeletionScheduleValid(action) {
		if (!action.scheduledAt || !action.windowEnd || !action.slotMinutes) return false;
		const scheduledAt = Date.parse(action.scheduledAt);
		const windowEnd = Date.parse(action.windowEnd);
		return Number.isFinite(scheduledAt)
			&& Number.isFinite(windowEnd)
			&& scheduledAt > windowEnd
			&& scheduledAt - windowEnd === action.slotMinutes * 60_000
			&& action.canSchedule
			&& Boolean(action.minimumToken);
	}

	async function submitFloorSchedule(action, floorId, scheduledDate = null) {
		const endpoint = action === 'cancel'
			? 'cancel-schedule'
			: action === 'deactivate'
				? 'deactivate'
				: null;
		if (!endpoint || !editingUrl) return;
		const url = new URL(editingUrl, window.location.origin);
		url.pathname = url.pathname.replace(/\/\d+$/, `/${floorId}/${endpoint}`);
		const payload = action === 'cancel'
			? { action: pendingAction.scheduledAction }
			: { scheduled_date: scheduledDate };
		const response = await fetch(url, {
			method: 'POST',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
			},
			body: JSON.stringify(payload),
		});
		if (followLoginRedirect(response)) return;
		const data = await response.json();
		if (!response.ok) {
			if (action === 'deactivate' && data.minimum_datetime) {
				const dateInput = $('[data-action-date]', actionDialog);
				dateInput.min = data.minimum_datetime;
				dateInput.value = data.minimum_datetime;
				$('[data-action-date-hint]', actionDialog).textContent =
					`Las reservaciones cambiaron; la fecha y hora mínima ahora es ${data.minimum_datetime}.`;
			}
			throw new Error(data.message || 'No se pudo actualizar la programación.');
		}

		const floor = floors.find((item) => item.id === floorId);
		if (floor) {
			if (action === 'cancel') {
				if (pendingAction.scheduledAction === 'delete') {
					floor.dateToBeDeleted = null;
				} else {
					floor.dateToBeDeactivated = null;
				}
			} else {
				floor.dateToBeDeleted = null;
				floor.dateToBeDeactivated = data.date_to_be_deactivated;
			}
			refreshFloorSchedule(floor);
		}
		actionDialog.close();
		await loadRows();
		showToast({
			title: action === 'cancel'
				? 'Programación cancelada'
				: 'Desactivación de piso programada',
			message: data.message,
		});
	}

	async function prepareDelete(button) {
		button.disabled = true;
		try {
			const clickedAtMs = Date.now();
			const response = await fetch(button.dataset.deletePreviewUrl, {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({ clicked_at_ms: clickedAtMs }),
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (!response.ok) throw new Error(data.message || 'No se pudo verificar el lote.');
			if (data.has_pending_reservations) {
				askForLotAction({
					button,
					url: button.dataset.deleteUrl,
					kind: 'delete',
					message: 'Este lote o alguno de sus pisos tiene reservaciones pendientes.',
					minimumDate: data.minimum_datetime,
					minimumToken: data.minimum_token,
					windowEnd: data.window_end,
					windowHours: data.window_hours,
					slotMinutes: data.slot_minutes,
					canSchedule: data.can_schedule,
				});
			} else {
				askForDeleteConfirmation(button);
			}
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo verificar el lote',
				message: error.message || 'Inténtalo de nuevo.',
			});
		} finally {
			button.disabled = false;
		}
	}

	async function postLotAction(button, title, payload = {}, decisionKind = null) {
		button.disabled = true;
		try {
			const actionUrl = button.dataset.actionUrl;
			const response = await fetch(actionUrl, {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify(payload),
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (response.status === 409 && decisionKind) {
				askForLotAction({
					button,
					url: actionUrl,
					kind: decisionKind,
					message: data.message,
					minimumDate: data.minimum_datetime,
					minimumToken: data.minimum_token,
					windowEnd: data.window_end,
					windowHours: data.window_hours,
					slotMinutes: data.slot_minutes,
					canSchedule: data.can_schedule,
					hasPendingReservations: data.has_pending_reservations,
				});
				return;
			}
			if (!response.ok) throw new Error(data.message || 'No se pudo completar la acción.');

			await loadRows();
			showToast({
				title: data.scheduled
					? (decisionKind === 'deactivate' ? 'Desactivación programada' : 'Eliminación programada')
					: title,
				message: data.message,
			});
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo actualizar el lote',
				message: error.message || 'Inténtalo de nuevo.',
			});
		} finally {
			button.disabled = false;
		}
	}

	tbody.addEventListener('click', (event) => {
		const target = event.target;
		if (!(target instanceof Element)) return;

		const toggle = target.closest('[data-lot-toggle]');
		if (toggle) {
			if (toggle.dataset.active === 'true') {
				void prepareParentDeactivation(toggle);
				return;
			}
			toggle.dataset.actionUrl = toggle.dataset.toggleUrl;
			void postLotAction(
				toggle,
				'Estado actualizado',
				{},
				null,
			);
			return;
		}

		const deleteButton = target.closest('[data-delete-lot]');
		if (!deleteButton) return;
		void prepareDelete(deleteButton);
	});

	$('[data-cancel-action]', actionDialog).addEventListener('click', () => {
		actionDialog.close();
	});
	$('[data-schedule-action]', actionDialog).addEventListener('click', () => {
		if (!pendingAction) return;
		if (pendingAction.kind === 'delete' || pendingAction.kind === 'floor-delete') {
			if (!isDeletionScheduleValid(pendingAction)) {
				showToast({
					tone: 'error',
					title: 'No se pudo programar la eliminación',
					message: 'La fecha no cumple el límite de reservaciones de este lote. Cierra y vuelve a abrir el diálogo.',
				});
				return;
			}
		} else if (!$('[data-action-date]', actionDialog).reportValidity()) {
			return;
		}
		if (pendingAction.kind === 'floor-delete') {
			const {
				floorId,
				floor,
				submitAfterDecision,
				minimumToken,
				scheduledAt,
			} = pendingAction;
			floorDeletionDecisions[floorId] = {
				scheduled_date: scheduledAt,
				minimum_token: minimumToken,
			};
			pendingAction = null;
			actionDialog.close();
			if (floor) removeFloorFromEditor(floor);
			if (submitAfterDecision) form.requestSubmit();
			return;
		}
		const {
			button,
			url,
			kind,
			minimumToken,
			scheduledAt,
		} = pendingAction;
		const scheduledDate = $('[data-action-date]', actionDialog).value;
		pendingAction = null;
		actionDialog.close();
		button.dataset.actionUrl = url;
		void postLotAction(button, 'Acción actualizada', {
			...(kind === 'delete'
				? { scheduled_date: scheduledAt }
				: kind === 'deactivate'
					? { scheduled_date: scheduledDate }
					: {}),
			...(minimumToken ? { minimum_token: minimumToken } : {}),
		}, kind);
	});
	$('[data-schedule-deactivation-action]', actionDialog).addEventListener('click', async () => {
		if (!pendingAction?.floor || !pendingAction.floorId) return;
		const dateInput = $('[data-action-date]', actionDialog);
		if (!dateInput.reportValidity()) return;
		const { floorId } = pendingAction;
		try {
			await submitFloorSchedule('deactivate', floorId, dateInput.value);
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo programar la desactivación',
				message: error.message || 'Inténtalo de nuevo.',
			});
		}
	});
	$('[data-cancel-schedule-action]', actionDialog).addEventListener('click', async () => {
		if (!pendingAction?.scheduledAction) return;
		if (pendingAction.floor && pendingAction.floorId) {
			const { floorId } = pendingAction;
			try {
				await submitFloorSchedule('cancel', floorId);
			} catch (error) {
				showToast({
					tone: 'error',
					title: 'No se pudo cancelar la programación',
					message: error.message || 'Inténtalo de nuevo.',
				});
			}
			return;
		}
		const { button, url, scheduledAction } = pendingAction;
		const cancelUrl = new URL(url, window.location.origin);
		cancelUrl.pathname = cancelUrl.pathname.replace(
			/\/deactivate$/,
			'/cancel-schedule',
		);
		button.disabled = true;
		try {
			const response = await fetch(cancelUrl, {
				method: 'POST',
				headers: {
					Accept: 'application/json',
					'Content-Type': 'application/json',
				},
				body: JSON.stringify({ action: scheduledAction }),
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (!response.ok) {
				throw new Error(data.message || 'No se pudo cancelar la programación.');
			}
			pendingAction = null;
			actionDialog.close();
			await loadRows();
			showToast({ title: 'Programación cancelada', message: data.message });
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo cancelar la programación',
				message: error.message || 'Inténtalo de nuevo.',
			});
		} finally {
			button.disabled = false;
		}
	});
	$('[data-override-action]', actionDialog).addEventListener('click', () => {
		if (!pendingAction) return;
		if (
			pendingAction.kind === 'floor-delete'
			|| pendingAction.kind === 'floor-confirm'
		) {
			const {
				floorId,
				floor,
				submitAfterDecision,
				kind,
			} = pendingAction;
			floorDeletionDecisions[floorId] = kind === 'floor-confirm'
				? { confirmed: true }
				: { override: true };
			pendingAction = null;
			actionDialog.close();
			if (floor) removeFloorFromEditor(floor);
			if (submitAfterDecision) form.requestSubmit();
			return;
		}
		const { button, url, kind, hasPendingReservations } = pendingAction;
		pendingAction = null;
		actionDialog.close();
		button.dataset.actionUrl = url;
		void postLotAction(
			button,
			kind === 'delete-confirm' ? 'Lote eliminado' : 'Acción completada',
			kind === 'delete-confirm'
				? { confirmed: true }
				: { override: kind === 'deactivate' ? hasPendingReservations : true },
			kind === 'delete-confirm' || kind === 'delete' ? 'delete' : null,
		);
	});
	actionDialog.addEventListener('close', () => {
		pendingAction = null;
	});

	filterButtons.forEach((button) => {
		button.addEventListener('click', () => {
			lotFilter = button.dataset.lotFilter;
			filterButtons.forEach((filterButton) => {
				filterButton.setAttribute(
					'aria-pressed',
					String(filterButton === button),
				);
			});
			updateCount();
		});
	});
	searchInput.addEventListener('input', updateCount);

	$('[data-open-create]').addEventListener('click', () => {
		resetForm();
		dialogMode = 'create';
		$('#create-lot-title').textContent = 'Crear nuevo lote';
		$('#create-lot-desc').textContent =
			'Los campos generales aplican a todo el lote. Selecciona un piso a la izquierda para definir su capacidad y rol.';
		$('[data-no-floors]').textContent =
			'Aún no hay pisos. Puedes crear el lote vacío y agregar pisos luego.';
		$('[data-no-floor-fields]').textContent =
			'Agrega un piso para definir su capacidad, espacios accesibles y rol. Un lote sin pisos no tiene espacios.';
		$('[data-submit-label]').textContent = submitLabel();
		dialog.showModal();
		$('#name', form).focus();
	});

	$$('[data-close-dialog]', dialog).forEach((button) => {
		button.addEventListener('click', () => dialog.close());
	});
	dialog.addEventListener('close', () => {
		if (toastLayer.childElementCount) bringToastsToFront();
	});
	$('[data-add-floor]').addEventListener('click', () => addFloor());
	form.addEventListener('submit', submit);
	form.addEventListener('input', (event) => {
		const input = event.target;
		if (input.getAttribute('aria-invalid') && !input.matches('[data-accessible]')) {
			setFieldError(input, '');
		}
		const panel = input.closest('[data-floor-panel]');
		if (panel) {
			checkAccessibleCapacity(panel);
			refreshFloors();
		}
	});

	loadRows();
})();
