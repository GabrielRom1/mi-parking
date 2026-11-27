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

	const DEFAULT_SLOT_MINUTES = 30;

	function ceilToSlot(isoValue, slotMinutes) {
		// isoValue: 'YYYY-MM-DDTHH:MM' (hora local de PR). Redondea hacia arriba al bloque.
		if (!isoValue) return isoValue;
		const [datePart, timePart = '00:00'] = isoValue.split('T');
		const [y, mo, d] = datePart.split('-').map(Number);
		const [h, mi] = timePart.split(':').map(Number);
		const date = new Date(y, mo - 1, d, h, mi);
		const remainder = (h * 60 + mi) % slotMinutes;
		if (remainder) date.setMinutes(date.getMinutes() + slotMinutes - remainder);
		const pad = (n) => String(n).padStart(2, '0');
		return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
	}

	function setSlotDateInput(dateInput, minimum, slotMinutes = DEFAULT_SLOT_MINUTES) {
		const value = ceilToSlot(minimum, slotMinutes);
		dateInput.type = 'datetime-local';
		dateInput.step = String(slotMinutes * 60);
		dateInput.min = value;
		dateInput.value = value;
		return value;
	}

	function setOverrideWarning({ kind, hasPending, count = null, visible = true }) {
		const warning = $('[data-override-warning]', actionDialog);
		warning.hidden = !visible || !hasPending;
		if (warning.hidden) return;
		const amount = Number.isInteger(count) && count > 0
			? (count === 1 ? '1 reservación activa' : `${count} reservaciones activas`)
			: 'todas las reservaciones activas';
		const verb = kind === 'delete' ? 'Eliminar' : 'Desactivar';
		$('[data-override-warning-text]', actionDialog).textContent =
			`${verb} ahora con override cancelará de inmediato ${amount} y se notificará por correo a los usuarios afectados. Se recomienda programar la acción en su lugar.`;
	}

	const pad2 = (n) => String(n).padStart(2, '0');

	function formatSlotTime(hours, minutes) {
		return new Date(2000, 0, 1, hours, minutes)
			.toLocaleTimeString('es-PR', { hour: 'numeric', minute: '2-digit' });
	}

	function formatDateTimeLabel(isoValue) {
		const [datePart, timePart] = isoValue.split('T');
		const [y, mo, d] = datePart.split('-').map(Number);
		const [h, mi] = timePart.split(':').map(Number);
		const dateLabel = new Date(y, mo - 1, d)
			.toLocaleDateString('es-PR', { day: 'numeric', month: 'short', year: 'numeric' });
		return `${dateLabel} · ${formatSlotTime(h, mi)}`;
	}

	function fillChoiceTimeOptions(minimum, slotMinutes) {
		const dateInput = $('[data-choice-date]', actionDialog);
		const timeSelect = $('[data-choice-time]', actionDialog);
		const [minDate, minTime] = minimum.split('T');
		const [minH, minM] = minTime.split(':').map(Number);
		const minMinutes = dateInput.value === minDate ? minH * 60 + minM : 0;
		const previous = timeSelect.value;
		timeSelect.replaceChildren();
		for (let total = 0; total < 24 * 60; total += slotMinutes) {
			if (total < minMinutes) continue;
			const h = Math.floor(total / 60);
			const m = total % 60;
			const option = document.createElement('option');
			option.value = `${pad2(h)}:${pad2(m)}`;
			option.textContent = formatSlotTime(h, m);
			timeSelect.append(option);
		}
		if ([...timeSelect.options].some((option) => option.value === previous)) {
			timeSelect.value = previous;
		}
	}

	// Actualiza la tarjeta "Programar desactivación" cuando el servidor devuelve un mínimo nuevo (409).
	function updateChoiceMinimum(minimumDatetime) {
		const card = $('[data-choice-card="schedule-deactivate"]', actionDialog);
		if (!minimumDatetime || $('[data-choice-mode]', actionDialog).hidden || card.hidden) return;
		const choiceDate = $('[data-choice-date]', actionDialog);
		const slot = Number(choiceDate.dataset.slot) || DEFAULT_SLOT_MINUTES;
		const minimum = ceilToSlot(minimumDatetime.slice(0, 16), slot);
		choiceDate.min = minimum.slice(0, 10);
		choiceDate.value = minimum.slice(0, 10);
		choiceDate.dataset.minimum = minimum;
		fillChoiceTimeOptions(minimum, slot);
		$('[data-choice-time]', actionDialog).value = minimum.slice(11, 16);
		$('[data-choice-hint]', card).textContent =
			`Las reservaciones cambiaron; la hora más temprana ahora es ${formatDateTimeLabel(minimum)}`;
		$('input[type="radio"]', card).checked = true;
		refreshChoiceConfirm();
	}

	function selectedChoice() {
		return $('[name="action-choice"]:checked', actionDialog)?.value ?? null;
	}

	function refreshChoiceConfirm() {
		if (!pendingAction) return;
		const choice = selectedChoice();
		$('[data-choice-confirm]', actionDialog).textContent =
			choice === 'schedule-delete'
				? 'Programar eliminación'
				: choice === 'schedule-deactivate'
					? 'Programar desactivación'
					: choice === 'override-deactivate' || pendingAction.kind === 'deactivate'
						? 'Desactivar ahora'
						: 'Eliminar ahora';
	}

	function hideChoiceMode() {
		$('[data-choice-mode]', actionDialog).hidden = true;
		$('[data-choice-confirm]', actionDialog).hidden = true;
	}

	/**
	 * Muestra el diálogo con tarjetas de opción (hay reservaciones pendientes).
	 * Cada tarjeta recibe null para ocultarla.
	 */
	function showChoiceMode({
		deleteCard = null,
		deactivateCard = null,
		overrideCard = { title: 'Override de emergencia', note: '' },
		overrideDeactivateCard = null,
		overrideCount = null,
	}) {
		['[data-action-date-field]', '[data-action-date-picker-field]',
			'[data-schedule-action]', '[data-schedule-deactivation-action]',
			'[data-override-action]', '[data-deactivate-now-action]',
			'[data-override-warning]']
			.forEach((selector) => { $(selector, actionDialog).hidden = true; });
		$('[data-choice-mode]', actionDialog).hidden = false;
		$('[data-choice-confirm]', actionDialog).hidden = false;

		const deleteEl = $('[data-choice-card="schedule-delete"]', actionDialog);
		const deactivateEl = $('[data-choice-card="schedule-deactivate"]', actionDialog);
		const overrideEl = $('[data-choice-card="override"]', actionDialog);
		const overrideDeactivateEl = $('[data-choice-card="override-deactivate"]', actionDialog);

		deleteEl.hidden = !deleteCard;
		if (deleteCard) {
			$('[data-choice-title]', deleteEl).textContent = deleteCard.title;
			$('[data-choice-desc]', deleteEl).textContent = deleteCard.description;
			$('[data-choice-fixed]', deleteEl).textContent = deleteCard.fixed;
			$('[data-choice-hint]', deleteEl).textContent = deleteCard.hint;
			$('input', deleteEl).disabled = !deleteCard.enabled;
		}

		deactivateEl.hidden = !deactivateCard;
		if (deactivateCard) {
			const slot = deactivateCard.slotMinutes || DEFAULT_SLOT_MINUTES;
			const minimum = ceilToSlot(deactivateCard.minimum, slot);
			$('[data-choice-title]', deactivateEl).textContent = deactivateCard.title;
			$('[data-choice-desc]', deactivateEl).textContent = deactivateCard.description;
			const choiceDate = $('[data-choice-date]', actionDialog);
			choiceDate.min = minimum.slice(0, 10);
			choiceDate.value = minimum.slice(0, 10);
			choiceDate.dataset.minimum = minimum;
			choiceDate.dataset.slot = String(slot);
			fillChoiceTimeOptions(minimum, slot);
			$('[data-choice-time]', actionDialog).value = minimum.slice(11, 16);
			$('[data-choice-hint]', deactivateEl).textContent =
				`Hora más temprana sin reservaciones: ${formatDateTimeLabel(minimum)}`;
			$('input[type="radio"]', deactivateEl).disabled = false;
		}

		const count = Number.isInteger(overrideCount) && overrideCount > 0 ? overrideCount : null;
		const affected = count === null
			? 'Todas las reservaciones afectadas se cancelan'
			: count === 1
				? 'La reservación afectada se cancela'
				: `Las ${count} reservaciones afectadas se cancelan`;
		const overrideText = `Aplica ahora. ${affected} y se notifica a esos usuarios por correo.`;
		overrideEl.hidden = !overrideCard;
		if (overrideCard) {
			$('[data-choice-title]', overrideEl).textContent = overrideCard.title;
			$('[data-choice-desc]', overrideEl).textContent =
				`${overrideText}${overrideCard.note ? ` ${overrideCard.note}` : ''}`;
		}
		overrideDeactivateEl.hidden = !overrideDeactivateCard;
		if (overrideDeactivateCard) {
			$('[data-choice-title]', overrideDeactivateEl).textContent = overrideDeactivateCard.title;
			$('[data-choice-desc]', overrideDeactivateEl).textContent =
				`${overrideText}${overrideDeactivateCard.note ? ` ${overrideDeactivateCard.note}` : ''}`;
		}

		// Marca la primera opción programable disponible; si ninguna, el override.
		const radios = [deleteEl, deactivateEl, overrideEl, overrideDeactivateEl]
			.filter((el) => !el.hidden)
			.map((el) => $('input[type="radio"]', el))
			.filter((radio) => !radio.disabled);
		radios.forEach((radio, index) => { radio.checked = index === 0; });
		refreshChoiceConfirm();
		actionDialog.showModal();
		radios[0]?.focus();
	}

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
		pendingReservationsCount = null,
	}) {
		const slot = slotMinutes || DEFAULT_SLOT_MINUTES;
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
		const isDelete = kind === 'delete';
		// Con reservaciones pendientes (y sin una acción ya programada) se usan tarjetas de opción.
		const choiceMode = hasPendingReservations && !scheduledAction;
		const target = lotName ? `«${lotName}»` : 'este lote';

		$('#action-dialog-title').textContent = isDelete
			? `¿Cómo deseas eliminar ${target}?`
			: `¿Cómo deseas desactivar ${target}?`;
		$('#action-dialog-desc').textContent = choiceMode
			? message
			: isDelete
				? `${message} Puedes programar la eliminación para la fecha fijada por el sistema o eliminarlo ahora.`
				: `${message} Puedes programar la desactivación para una fecha y hora o desactivarlo ahora.`;

		hideChoiceMode();
		$('[data-override-warning]', actionDialog).hidden = true;
		$('[data-deactivate-now-action]', actionDialog).hidden = true;
		$('[data-schedule-deactivation-action]', actionDialog).hidden = true;
		$('[data-cancel-schedule-action]', actionDialog).hidden = !scheduledAction;

		const minimumSlot = isDelete ? minimumDate : ceilToSlot(minimumDate, slot);

		if (choiceMode) {
			const description = 'El lote sigue activo hasta la hora programada. No se cancela ninguna reservación; las nuevas reservaciones que pasen de esa hora quedan bloqueadas.';
			showChoiceMode({
				deleteCard: isDelete ? {
					title: 'Programar para después (recomendado)',
					description,
					fixed: formatDateTimeLabel(minimumDate.slice(0, 16)),
					hint: canSchedule
						? `La fecha la fija el sistema: ${windowHours} horas y ${slot} minutos después de abrir este diálogo.`
						: 'No se puede programar: hay reservaciones que terminan después de esa fecha.',
					enabled: canSchedule,
				} : null,
				deactivateCard: isDelete ? null : {
					title: 'Programar para después (recomendado)',
					description,
					minimum: minimumDate,
					slotMinutes: slot,
				},
				overrideCount: pendingReservationsCount,
			});
			return;
		}

		// Sin reservaciones pendientes (o con una acción ya programada): diseño simple.
		$('[data-action-date-field]', actionDialog).hidden =
			!isDelete && !scheduledAt;
		$('[data-action-date-picker-field]', actionDialog).hidden = isDelete
			|| Boolean(scheduledAt);
		$('[data-override-action]', actionDialog).hidden = Boolean(scheduledAction);
		$('[data-schedule-action]', actionDialog).hidden =
			!canSchedule || Boolean(scheduledAction);
		$('[data-schedule-action]', actionDialog).textContent =
			isDelete ? 'Programar eliminación' : 'Programar desactivación';
		const dateInput = $('[data-action-date]', actionDialog);
		if (isDelete) {
			dateInput.type = 'date';
			dateInput.step = '1';
			dateInput.min = minimumDate.slice(0, 10);
			dateInput.value = minimumDate.slice(0, 10);
		} else {
			setSlotDateInput(dateInput, minimumDate, slot);
		}
		$('[data-action-date-hint]', actionDialog).textContent =
			`La fecha y hora mínima es ${formatDateTimeLabel(minimumSlot.slice(0, 16))} (bloques de ${slot} minutos).`;
		$('[data-action-datetime-display]', actionDialog).textContent =
			isDelete
				? formatDateTimeLabel(minimumDate.slice(0, 16))
				: scheduledAt
					? scheduledAt.replace('T', ' ')
					: '';
		$('[data-action-date-field] > span:first-child', actionDialog).textContent =
			isDelete ? 'Eliminación programada' : 'Desactivación programada';
		$('[data-deletion-date-hint]', actionDialog).textContent = canSchedule
			? isDelete
				? `Programada automáticamente para ${windowHours} horas y ${slot} minutos después de abrir este diálogo.`
				: 'Al llegar la fecha y hora, el scheduler marcará el lote y sus pisos como inactivos.'
			: 'No se puede programar mientras el lote tenga una eliminación programada; cancélala primero.';
		$('[data-override-action]', actionDialog).textContent =
			isDelete ? 'Eliminar ahora' : 'Desactivar ahora';
		actionDialog.showModal();
		$('[data-schedule-action]', actionDialog).hidden
			? $('[data-override-action]', actionDialog).focus()
			: $('[data-schedule-action]', actionDialog).focus();
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
		hideChoiceMode();
		const canRemoveFloor = !floor || floor.canRemove;
		const canDeleteFloor = canRemoveFloor && !hasScheduledDeletion;
		const floorIsActive = Boolean(floor) && floor.isActive !== false;
		const canScheduleDeactivation = floorIsActive && !hasScheduledDeactivation
			&& Boolean(issue.minimum_deactivation_datetime);
		const canDeactivateNow = floorIsActive && !inheritedSchedule;
		$('[data-deactivate-now-action]', actionDialog).hidden = true;
		if (hasPending && !inheritedSchedule && (canDeleteFloor || canDeactivateNow)) {
			$('#action-dialog-desc').textContent = 'El piso tiene reservaciones pendientes.';
			$('[data-cancel-schedule-action]', actionDialog).hidden =
				!floor || !pendingAction.scheduledAction;
			const slot = issue.slot_minutes || DEFAULT_SLOT_MINUTES;
			const keepsDescription = 'No se cancela ninguna reservación; las nuevas reservaciones que pasen de esa hora quedan bloqueadas.';
			showChoiceMode({
				deleteCard: canDeleteFloor ? {
					title: 'Programar eliminación (recomendado)',
					description: `El piso sigue activo hasta la fecha programada. ${keepsDescription}`,
					fixed: formatDateTimeLabel(issue.minimum_datetime.slice(0, 16)),
					hint: issue.can_schedule
						? `La fecha la fija el sistema: ${issue.window_hours} horas y ${slot} minutos después de abrir este diálogo.`
						: 'No se puede programar: hay reservaciones que terminan después de esa fecha.',
					enabled: issue.can_schedule,
				} : null,
				deactivateCard: canScheduleDeactivation ? {
					title: canDeleteFloor
						? 'Programar desactivación'
						: 'Programar desactivación (recomendado)',
					description: `El piso se conserva y sigue activo hasta la hora programada. ${keepsDescription}`,
					minimum: issue.minimum_deactivation_datetime,
					slotMinutes: slot,
				} : null,
				overrideCard: canDeleteFloor ? {
					title: 'Override: eliminar ahora',
					note: 'El piso se elimina al guardar los cambios del lote.',
				} : null,
				overrideDeactivateCard: canDeactivateNow ? {
					title: 'Override: desactivar ahora',
					note: 'El piso se conserva y queda inactivo de inmediato.',
				} : null,
				overrideCount: issue.pending_reservations_count,
			});
			return;
		}
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
		const floorSlotMinutes = issue.slot_minutes || DEFAULT_SLOT_MINUTES;
		const minimumShown = minimumDeactivationDate
			? setSlotDateInput(dateInput, minimumDeactivationDate, floorSlotMinutes)
			: '';
		$('[data-action-date-hint]', actionDialog).textContent =
			`La desactivación no puede ser antes del ${minimumShown.replace('T', ' ')} (bloques de ${floorSlotMinutes} minutos).`;
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
		$('[data-deactivate-now-action]', actionDialog).hidden = !canDeactivateNow;
		if (!floor) {
			$('[data-schedule-deactivation-action]', actionDialog).hidden = true;
			$('[data-cancel-schedule-action]', actionDialog).hidden = true;
			$('[data-action-date-picker-field]', actionDialog).hidden = true;
		}
		setOverrideWarning({
			kind: 'delete',
			hasPending,
			count: issue.pending_reservations_count,
			visible: !$('[data-override-action]', actionDialog).hidden,
		});
		actionDialog.showModal();
		const preferredFloorAction = [
			'[data-schedule-action]',
			'[data-schedule-deactivation-action]',
			'[data-override-action]',
		].map((selector) => $(selector, actionDialog)).find((el) => !el.hidden);
		preferredFloorAction?.focus();
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
				pendingReservationsCount: data.pending_reservations_count,
				slotMinutes: data.slot_minutes,
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
			: action === 'deactivate' || action === 'deactivate-now'
				? 'deactivate'
				: null;
		if (!endpoint || !editingUrl) return;
		const url = new URL(editingUrl, window.location.origin);
		url.pathname = url.pathname.replace(/\/\d+$/, `/${floorId}/${endpoint}`);
		const payload = action === 'cancel'
			? { action: pendingAction.scheduledAction }
			: action === 'deactivate-now'
				? { override: true }
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
				setSlotDateInput(dateInput, data.minimum_datetime);
				updateChoiceMinimum(data.minimum_datetime);
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
			} else if (action === 'deactivate-now') {
				floor.isActive = false;
				floor.dateToBeDeactivated = null;
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
				: action === 'deactivate-now'
					? 'Piso desactivado'
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
			askForLotAction({
				button,
				url: button.dataset.deleteUrl,
				kind: 'delete',
				lotName: button.closest('[data-lot-name]')?.dataset.lotName,
				message: data.has_pending_reservations
					? 'El lote o sus pisos tienen reservaciones pendientes.'
					: 'El lote y sus pisos no tienen reservaciones pendientes.',
				minimumDate: data.minimum_datetime,
				minimumToken: data.minimum_token,
				windowEnd: data.window_end,
				windowHours: data.window_hours,
				slotMinutes: data.slot_minutes,
				canSchedule: data.can_schedule,
				hasPendingReservations: data.has_pending_reservations,
				pendingReservationsCount: data.pending_reservations_count,
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
					pendingReservationsCount: data.pending_reservations_count,
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
	$('[data-deactivate-now-action]', actionDialog).addEventListener('click', async () => {
		if (!pendingAction?.floor || !pendingAction.floorId) return;
		try {
			await submitFloorSchedule('deactivate-now', pendingAction.floorId);
		} catch (error) {
			showToast({
				tone: 'error',
				title: 'No se pudo desactivar el piso',
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
	$('[data-choice-mode]', actionDialog).addEventListener('change', (event) => {
		if (event.target.matches('[data-choice-date]')) {
			fillChoiceTimeOptions(
				event.target.dataset.minimum,
				Number(event.target.dataset.slot) || DEFAULT_SLOT_MINUTES,
			);
		}
		if (event.target.matches('[data-choice-date], [data-choice-time]')) {
			$('[data-choice-card="schedule-deactivate"] input[type="radio"]', actionDialog).checked = true;
		}
		refreshChoiceConfirm();
	});
	$('[data-choice-confirm]', actionDialog).addEventListener('click', () => {
		if (!pendingAction) return;
		const choice = selectedChoice();
		if (choice === 'override') {
			$('[data-override-action]', actionDialog).click();
		} else if (choice === 'override-deactivate') {
			$('[data-deactivate-now-action]', actionDialog).click();
		} else if (choice === 'schedule-delete') {
			$('[data-schedule-action]', actionDialog).click();
		} else if (choice === 'schedule-deactivate') {
			const choiceDate = $('[data-choice-date]', actionDialog);
			const choiceTime = $('[data-choice-time]', actionDialog);
			if (!choiceDate.reportValidity()) return;
			if (!choiceDate.value || !choiceTime.value) {
				showToast({
					tone: 'error',
					title: 'Fecha u hora incompleta',
					message: 'Escoge una fecha y una hora para programar la desactivación.',
				});
				return;
			}
			const dateInput = $('[data-action-date]', actionDialog);
			dateInput.type = 'datetime-local';
			dateInput.min = '';
			dateInput.value = `${choiceDate.value}T${choiceTime.value}`;
			$(pendingAction.floor
				? '[data-schedule-deactivation-action]'
				: '[data-schedule-action]', actionDialog).click();
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
			kind === 'delete' ? 'Lote eliminado' : 'Acción completada',
			{ override: kind === 'deactivate' ? hasPendingReservations : true },
			kind === 'delete' ? 'delete' : null,
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
