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
				dateLabel.dateTime = date;
				dateLabel.textContent = new Intl.DateTimeFormat('es', {
					day: 'numeric',
					month: 'short',
				}).format(new Date(`${date}T00:00:00`));
				dateLabel.hidden = false;
			} else {
				dateLabel.hidden = true;
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
		$('[data-remove-floor]', item).hidden = index !== floors.length - 1;

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
		$('[data-floor-select]', item).addEventListener('click', () => selectFloor(index));
		$('[data-remove-floor]', item).addEventListener('click', removeTopFloor);
		$('[data-capacity]', panel).value = floorData?.capacity ?? '';
		$('[data-accessible]', panel).value = floorData?.accessible_capacity ?? '';
		$('[name$="-role_id"]', panel).value = floorData?.role_id ?? '';
		floorList.prepend(item);
		floorPanels.append(panel);
		floors.push({ id: floorData?.id ?? null, item, panel });
		selectFloor(index);
	}

	function removeTopFloor() {
		const floor = floors.pop();
		if (!floor) return;
		floor.item.remove();
		floor.panel.remove();
		selectFloor(floors.length - 1);
		$('[data-add-floor]').focus();
	}

	function resetForm() {
		form.reset();
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
				showToast({ title: 'Lote actualizado', message: data.message });
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

	async function postLotAction(button, title) {
		button.disabled = true;
		try {
			const response = await fetch(button.dataset.actionUrl, {
				method: 'POST',
				headers: { Accept: 'application/json' },
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json();
			if (!response.ok) throw new Error(data.message || 'No se pudo completar la acción.');

			await loadRows();
			showToast({
				title: data.scheduled ? 'Eliminación programada' : title,
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
			toggle.dataset.actionUrl = toggle.dataset.toggleUrl;
			void postLotAction(toggle, 'Estado actualizado');
			return;
		}

		const deleteButton = target.closest('[data-delete-lot]');
		if (!deleteButton) return;
		if (!window.confirm(
			'¿Seguro de eliminar este lote? Si tiene reservaciones, su eliminación se programará para más adelante.',
		)) return;
		deleteButton.dataset.actionUrl = deleteButton.dataset.deleteUrl;
		void postLotAction(deleteButton, 'Lote eliminado');
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
