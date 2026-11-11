// Lot Management (admin): list loading states, Create lot dialog, toasts.
(() => {
	const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

	const $ = (selector, root = document) => root.querySelector(selector);
	const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

	const table = $('[data-lots-table]');
	const tbody = $('[data-lots-body]');
	const skeletonHtml = tbody.innerHTML;
	const listStatus = $('[data-lots-status]');
	const countLabel = $('[data-lots-count]');

	// ---------------------------------------------------------------- Toasts
	const toastLayer = $('[data-toasts]');

	function bringToastsToFront() {
		// A manual popover shares the top layer with the modal; re-showing it puts it last (on top).
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
		setTimeout(remove, 400); // fallback if the animation never fires
	}

	function showToast({ tone = 'success', title, message }) {
		const toast = $('#toast-template').content.firstElementChild.cloneNode(true);
		toast.dataset.tone = tone;
		toast.setAttribute('role', tone === 'error' ? 'alert' : 'status');
		$('[data-toast-title]', toast).textContent = title;
		$('[data-toast-message]', toast).textContent = message;
		$('[data-toast-close]', toast).addEventListener('click', () => dismissToast(toast));
		// One notice at a time, so they never pile up over the toolbar's Create lot button.
		toastLayer.replaceChildren(toast);
		bringToastsToFront();
		setTimeout(() => dismissToast(toast), tone === 'error' ? 8000 : 5000);
	}

	// ------------------------------------------------------------------ List
	// When a session expires, the server answers fetches with a redirect to the login page.
	function followLoginRedirect(response) {
		if (response.redirected) window.location.assign(response.url);
		return response.redirected;
	}

	function lotRows() {
		return $$('tr[data-lot-id]', tbody);
	}

	function updateCount() {
		const count = lotRows().length;
		countLabel.hidden = count === 0;
		countLabel.textContent = `${count} ${count === 1 ? 'lote' : 'lotes'}`;
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
			const response = await fetch(table.dataset.rowsUrl, { headers: { Accept: 'text/html' } });
			if (followLoginRedirect(response)) return;
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			tbody.innerHTML = await response.text();
			setListState('ready');
			updateCount();
		} catch (error) {
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
			loadRows(); // the full list will include the new lot
			return;
		}

		$('[data-empty-state]', tbody)?.remove();
		// The server computes the keys, so this always matches the order after a reload.
		const next = lotRows().find((other) => other.dataset.sortKey > row.dataset.sortKey);
		tbody.insertBefore(row, next ?? null);
		updateCount();

		row.scrollIntoView({ block: 'nearest', behavior: reduceMotion.matches ? 'auto' : 'smooth' });
		row.dataset.new = '';
		setTimeout(() => delete row.dataset.new, 2400);
	}

	// ---------------------------------------------------------------- Dialog
	const dialog = $('[data-create-dialog]');
	const form = $('[data-create-form]');
	const floorList = $('[data-floor-list]');
	const floorPanels = $('[data-floor-panels]');
	const submitButton = $('[data-submit]');
	let floors = []; // [{ item, panel }], index 0 = Floor 1 (bottom)
	let selected = -1;
	let submitting = false;
	const submitLabel = () => (floors.length ? 'Crear lote' : 'Crear lote vacío');

	function fromTemplate(id, index) {
		const html = $(id).innerHTML.replaceAll('__i__', index).replaceAll('__n__', index + 1);
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
		refreshFloors();
	}

	const pluralize = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`;
	const spotsSummary = (spots, accessible) => `${pluralize(spots, 'espacio')} · ${pluralize(accessible, 'accesible')}`;

	const numberValue = (input) => (input.value.trim() === '' ? null : Number(input.value));

	function refreshFloorItem({ item, panel }, index) {
		const selectButton = $('[data-floor-select]', item);
		const summary = $('[data-floor-summary]', item);
		const isSelected = index === selected;
		const isTopFloor = index === floors.length - 1;

		panel.hidden = !isSelected;
		selectButton.setAttribute('aria-current', String(isSelected));
		$('[data-remove-floor]', item).hidden = !isTopFloor;

		if ($('[aria-invalid]', panel)) {
			selectButton.dataset.invalid = '';
			summary.textContent = 'Necesita atención';
			return;
		}
		delete selectButton.dataset.invalid;
		const capacity = numberValue($('[data-capacity]', panel));
		const accessible = numberValue($('[data-accessible]', panel));
		summary.textContent = capacity === null ? 'Sin configurar' : spotsSummary(capacity, accessible ?? 0);
	}

	function sumAcrossFloors(inputSelector) {
		return floors.reduce((total, { panel }) => total + (numberValue($(inputSelector, panel)) || 0), 0);
	}

	function refreshFloors() {
		const hasFloors = floors.length > 0;
		$('[data-floor-count]').textContent = floors.length;
		$('[data-no-floors]').hidden = hasFloors;
		$('[data-no-floor-fields]').hidden = hasFloors;
		$('[data-floor-heading]').textContent = selected >= 0
			? `Campos por piso · Piso ${selected + 1}`
			: 'Campos por piso';
		$('[data-lot-total]').textContent = spotsSummary(
			sumAcrossFloors('[data-capacity]'),
			sumAcrossFloors('[data-accessible]'),
		);
		if (!submitting) $('[data-submit-label]', submitButton).textContent = submitLabel();
		floors.forEach(refreshFloorItem);
	}

	function selectFloor(index) {
		selected = index;
		refreshFloors();
	}

	function checkAccessibleCapacity(panel) {
		// Live version of the server rule so the error shows while typing.
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

	function addFloor() {
		const index = floors.length;
		const item = fromTemplate('#floor-item-template', index);
		const panel = fromTemplate('#floor-panel-template', index);
		$('[data-floor-select]', item).addEventListener('click', () => selectFloor(index));
		$('[data-remove-floor]', item).addEventListener('click', removeTopFloor);
		floorList.prepend(item); // new floors go on top
		floorPanels.append(panel);
		floors.push({ item, panel });
		selectFloor(index);
		$('[data-capacity]', panel).focus();
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
		clearAllErrors();
	}

	function setSubmitting(isSubmitting) {
		submitting = isSubmitting;
		submitButton.disabled = isSubmitting;
		submitButton.setAttribute('aria-busy', String(isSubmitting));
		$('[data-submit-idle]', submitButton).hidden = isSubmitting;
		$('[data-submit-busy]', submitButton).hidden = !isSubmitting;
		$('[data-submit-label]', submitButton).textContent = isSubmitting ? 'Creando…' : submitLabel();
	}

	function showServerErrors(errors) {
		for (const [name, message] of Object.entries(errors)) {
			const input = form.elements.namedItem(name);
			if (input && input.type !== 'hidden') setFieldError(input, message);
		}
		// Focus the first problem: lot-wide fields come first, then the lowest floor with errors.
		const invalidLotField = $('#name[aria-invalid], #location[aria-invalid]', form);
		const invalidFloorField = $('[aria-invalid]', floorPanels);
		if (!invalidLotField && invalidFloorField) {
			selected = floors.findIndex(({ panel }) => panel.contains(invalidFloorField)); // show it so it can take focus
		}
		refreshFloors();
		(invalidLotField ?? invalidFloorField)?.focus();
	}

	const showFailure = (message) => showToast({ tone: 'error', title: 'No se pudo crear el lote', message });

	async function submit(event) {
		event.preventDefault();
		if (submitting) return; // block double submits
		clearAllErrors();
		setSubmitting(true);
		try {
			const response = await fetch(form.action, {
				method: 'POST',
				body: new FormData(form),
				headers: { Accept: 'application/json' },
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json().catch(() => ({}));

			if (response.ok) {
				dialog.close();
				resetForm();
				insertRow(data.row_html);
				showToast({ title: 'Lote creado', message: data.message });
				return;
			}
			if (data.errors) showServerErrors(data.errors);
			showFailure(data.message || 'Algo salió mal. Inténtalo de nuevo en un momento.');
		} catch (error) {
			showFailure('No se pudo conectar con el servidor. Revisa tu conexión e inténtalo de nuevo.');
		} finally {
			setSubmitting(false);
		}
	}

	// ----------------------------------------------------------------- Wire up

	$('[data-open-create]').addEventListener('click', () => {
		resetForm();
		dialog.showModal();
		$('#name', form).focus();
	});
	$$('[data-close-dialog]', dialog).forEach((button) => button.addEventListener('click', () => dialog.close()));
	dialog.addEventListener('close', () => {
		if (toastLayer.childElementCount) bringToastsToFront();
	});
	$('[data-add-floor]').addEventListener('click', addFloor);
	form.addEventListener('submit', submit);
	form.addEventListener('input', (event) => {
		const input = event.target;
		// Editing a field clears its error; the accessible-capacity rule is re-checked live.
		if (input.getAttribute('aria-invalid') && !input.matches('[data-accessible]')) setFieldError(input, '');
		const panel = input.closest('[data-floor-panel]');
		if (panel) {
			checkAccessibleCapacity(panel);
			refreshFloors();
		}
	});

	loadRows();
})();
