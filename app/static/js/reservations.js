// Reserve page (SRS REQ.3.1, SDS Screen #4 with Figma Option B): drag a time on the
// availability chart, pick a lot, pick a spot, confirm. The toolbar searches and sorts
// the lots, and Quick Find suggests a spot (SRS Feature 5). Styling lives in the
// templates; this file only toggles attributes and swaps in HTML the server renders.
(() => {
	const $ = (selector, root = document) => root.querySelector(selector);
	const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

	const page = $('[data-reserve-page]');
	if (!page) return;

	const chartHolder = $('[data-chart]', page);
	const lotsHolder = $('[data-lots]', page);
	const lotSelect = $('[data-chart-lot]', page);
	const rangeLabel = $('[data-range-label]', page);
	const searchInput = $('[data-search]', page);
	const sortSelect = $('[data-sort]', page);
	const accessibleBox = $('[data-accessible]', page); // only rendered for users who need an accessible spot
	const dialog = $('[data-reserve-dialog]');
	const dialogBody = $('[data-dialog-body]', dialog);
	const baseUrl = page.dataset.baseUrl;

	const state = {
		start: page.dataset.start, // the time picked on the chart, 'YYYY-MM-DDTHH:MM', Puerto Rico time
		end: page.dataset.end,
		lotId: null, // the lot being reserved in the dialog
		spotId: null,
		dialogStart: null, // the time being reserved in the dialog: the chart's, or Quick Find's
		dialogEnd: null,
		reserved: false, // refresh the chart and lots when the dialog closes
		holding: false, // a Quick Find suggestion is held; release it if the dialog closes without reserving
	};

	function accessibleOnly() {
		return accessibleBox?.checked ? '1' : '';
	}

	// When a session expires, the server answers fetches with a redirect to the login page.
	function followLoginRedirect(response) {
		if (response.redirected) window.location.assign(response.url);
		return response.redirected;
	}

	function withParams(url, params) {
		const query = new URLSearchParams();
		for (const [key, value] of Object.entries(params)) {
			if (value !== null && value !== undefined && value !== '') query.set(key, value);
		}
		return `${url}?${query}`;
	}

	async function fetchHtml(url) {
		const response = await fetch(url, { headers: { Accept: 'text/html' } });
		if (followLoginRedirect(response)) return null;
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		return response.text();
	}

	// ------------------------------------------------------------------ Chart
	function columnOf(cell) {
		return cell.closest('[data-column]');
	}

	function openCell(element) {
		const cell = element?.closest?.('[data-cell]');
		return cell && cell.dataset.state === 'open' && chartHolder.contains(cell) ? cell : null;
	}

	function selectedCells() {
		const first = $(`[data-cell][data-start="${state.start}"]`, chartHolder);
		const last = $(`[data-cell][data-end="${state.end}"]`, chartHolder);
		if (!first || !last || columnOf(first) !== columnOf(last)) return null;
		return [first, last];
	}

	function showSelection() {
		$$('[data-selection]', chartHolder).forEach((overlay) => { overlay.hidden = true; });
		const cells = selectedCells();
		if (!cells) return;
		const [first, last] = cells;
		const overlay = $('[data-selection]', columnOf(first));
		overlay.style.top = `${first.offsetTop - 3}px`;
		overlay.style.height = `${last.offsetTop + last.offsetHeight - first.offsetTop + 6}px`;
		overlay.hidden = false;
		rangeLabel.textContent = `${columnOf(first).dataset.dayLabel} · ${first.dataset.label} – ${last.dataset.endLabel}`;
	}

	let drag = null;

	function selectBetween(anchor, cell) {
		const cells = $$('[data-cell]', columnOf(anchor));
		const [first, last] = cells.indexOf(anchor) <= cells.indexOf(cell) ? [anchor, cell] : [cell, anchor];
		state.start = first.dataset.start;
		state.end = last.dataset.end;
		showSelection();
	}

	chartHolder.addEventListener('pointerdown', (event) => {
		const cell = openCell(event.target);
		if (!cell) return;
		event.preventDefault();
		drag = cell;
		chartHolder.setPointerCapture(event.pointerId);
		selectBetween(cell, cell);
	});

	chartHolder.addEventListener('pointermove', (event) => {
		if (!drag) return;
		const cell = openCell(document.elementFromPoint(event.clientX, event.clientY));
		// Open cells in a day are contiguous, so any open cell in the same column extends the range.
		if (cell && columnOf(cell) === columnOf(drag)) selectBetween(drag, cell);
	});

	function endDrag() {
		if (!drag) return;
		drag = null;
		loadLots();
	}
	chartHolder.addEventListener('pointerup', endDrag);
	chartHolder.addEventListener('pointercancel', endDrag);

	let chartRequest = 0;
	async function loadChart() {
		const request = ++chartRequest;
		chartHolder.setAttribute('aria-busy', 'true');
		try {
			const html = await fetchHtml(withParams(page.dataset.chartUrl, {
				lot: lotSelect.value, accessible: accessibleOnly(),
			}));
			if (html === null || request !== chartRequest) return;
			chartHolder.innerHTML = html;
			showSelection();
		} catch (error) {
			// Keep the chart that's on screen; the next change tries again.
		} finally {
			if (request === chartRequest) chartHolder.removeAttribute('aria-busy');
		}
	}

	// ------------------------------------------------------------------ Lots
	let lotsRequest = 0;
	async function loadLots() {
		const request = ++lotsRequest;
		lotsHolder.setAttribute('aria-busy', 'true');
		try {
			const html = await fetchHtml(withParams(page.dataset.lotsUrl, {
				start: state.start,
				end: state.end,
				lot: lotSelect.value,
				q: searchInput.value.trim(),
				sort: sortSelect.value,
				accessible: accessibleOnly(),
			}));
			if (html === null || request !== lotsRequest) return;
			lotsHolder.innerHTML = html;
		} catch (error) {
			lotsHolder.insertAdjacentHTML('afterbegin',
				'<p role="alert" class="mb-3 rounded-lg bg-[#fff0f2] px-3 py-2 font-semibold text-[#b00020]">No se pudo actualizar la lista de lotes. Inténtalo de nuevo.</p>');
		} finally {
			if (request === lotsRequest) lotsHolder.removeAttribute('aria-busy');
		}
	}

	function showLotInChart(lotId) {
		if (lotSelect.value === String(lotId)) return;
		lotSelect.value = String(lotId);
		loadChart();
		loadLots();
	}

	lotSelect.addEventListener('change', () => {
		loadChart();
		loadLots();
	});

	// ------------------------------------------------------------------ Search (REQ.5.2)
	let searchTimer = null;
	searchInput.addEventListener('input', () => {
		clearTimeout(searchTimer);
		searchTimer = setTimeout(loadLots, 250);
	});
	sortSelect.addEventListener('change', loadLots);
	accessibleBox?.addEventListener('change', () => {
		loadChart();
		loadLots();
	});

	lotsHolder.addEventListener('click', (event) => {
		const reserveButton = event.target.closest('[data-reserve]');
		if (reserveButton) {
			showLotInChart(reserveButton.dataset.lotId);
			openReserveDialog(reserveButton.dataset.lotId);
			return;
		}
		// Opening a card's "Ver espacios por tipo" shouldn't also filter the chart.
		if (event.target.closest('[data-lot-details]')) return;
		const card = event.target.closest('[data-lot-card]');
		if (card && !card.querySelector('[data-reserve]')?.disabled) showLotInChart(card.dataset.lotId);
	});

	// ------------------------------------------------------------------ Dialog
	function showDialogError(message) {
		dialogBody.innerHTML = `<div class="flex flex-col gap-4 p-5 sm:p-7">
			<p role="alert" class="rounded-lg bg-[#fff0f2] px-4 py-3 font-semibold text-[#b00020]"></p>
			<div class="flex justify-end"><button type="button" data-close-dialog class="h-10 cursor-pointer rounded-lg border border-gray-300 px-4 font-semibold hover:bg-gray-50">Cerrar</button></div>
		</div>`;
		$('[role=alert]', dialogBody).textContent = message;
	}

	async function showStep(url) {
		try {
			const html = await fetchHtml(url);
			if (html === null) return;
			dialogBody.innerHTML = html;
			if (!dialog.open) dialog.showModal();
			($('[aria-selected=true]', dialogBody) || $('button:not([disabled])', dialogBody))?.focus();
		} catch (error) {
			showDialogError('No se pudo cargar este paso. Inténtalo de nuevo en un momento.');
			if (!dialog.open) dialog.showModal();
		}
	}

	function openReserveDialog(lotId) {
		state.lotId = lotId;
		state.spotId = null;
		state.dialogStart = state.start;
		state.dialogEnd = state.end;
		showChooseSpot();
	}

	function showChooseSpot() {
		showStep(withParams(`${baseUrl}lots/${state.lotId}/spots`, {
			start: state.dialogStart, end: state.dialogEnd, spot: state.spotId, accessible: accessibleOnly(),
		})).then(() => {
			const selected = $('[data-spot-tile][data-selected]', dialogBody);
			if (selected) pickSpot(selected);
		});
	}

	function pickSpot(tile) {
		$$('[data-spot-tile][data-selected]', dialogBody).forEach((other) => other.removeAttribute('data-selected'));
		tile.setAttribute('data-selected', '');
		state.spotId = tile.dataset.spotId;
		const summary = $('[data-spot-summary]', dialogBody);
		$('[data-spot-summary-title]', summary).textContent = `Espacio ${tile.dataset.label} · Piso ${tile.dataset.floor}`;
		$('[data-spot-summary-text]', summary).textContent = `Libre durante todo tu horario (${summary.dataset.time}).`;
		$('[data-continue]', dialogBody).disabled = false;
	}

	function showFloor(tab) {
		$$('[data-floor-tab]', dialogBody).forEach((other) => other.setAttribute('aria-selected', String(other === tab)));
		$$('[data-floor-panel]', dialogBody).forEach((panel) => {
			panel.hidden = panel.dataset.floorPanel !== tab.dataset.floorTab;
		});
	}

	dialogBody.addEventListener('click', (event) => {
		const target = event.target;
		if (target.closest('[data-close-dialog]')) dialog.close();
		else if (target.closest('[data-floor-tab]')) showFloor(target.closest('[data-floor-tab]'));
		else if (target.closest('[data-spot-tile]:not([disabled])')) pickSpot(target.closest('[data-spot-tile]'));
		else if (target.closest('[data-continue]:not([disabled])')) showConfirm();
		else if (target.closest('[data-change-spot]')) showChooseSpot();
		else if (target.closest('[data-quick-find-reserve]')) reserveSuggestion(target.closest('[data-quick-find-form]'));
	});

	function showConfirm() {
		showStep(withParams(`${baseUrl}spots/${state.spotId}/confirm`, {
			start: state.dialogStart, end: state.dialogEnd,
		}));
	}

	// ------------------------------------------------------------------ Quick Find (REQ.5.1)
	// The dialog (Figma "4 · Quick Find") shows its best match right away, so opening it is a search.
	function csrfBody() {
		const body = new FormData();
		body.set('csrf_token', page.dataset.csrf);
		return body;
	}

	$('[data-quick-find]', page).addEventListener('click', () => postQuickFind(page.dataset.quickFindUrl, csrfBody()));

	// "Búsqueda rápida en este horario": the same dialog, with the chart's time and lot.
	$('[data-quick-find-range]', page).addEventListener('click', () => {
		const body = csrfBody();
		body.set('start_time', state.start);
		body.set('end_time', state.end);
		// Quick Find only offers active lots, so an inactive one picked on the chart is left out.
		if (lotSelect.selectedOptions[0]?.hasAttribute('data-active')) body.set('lot', lotSelect.value);
		postQuickFind(page.dataset.quickFindUrl, body);
	});

	async function postQuickFind(url, body) {
		try {
			const response = await fetch(url, { method: 'POST', body, headers: { Accept: 'text/html' } });
			if (followLoginRedirect(response)) return;
			if (response.status >= 500) throw new Error(`HTTP ${response.status}`);
			dialogBody.innerHTML = await response.text(); // the result, or the form with its error (422)
			state.holding = Boolean($('[data-quick-find-form][data-spot-id]', dialogBody));
			if (!dialog.open) dialog.showModal();
			($('[data-quick-find-reserve]', dialogBody) || $('[data-close-dialog]:not([aria-label])', dialogBody))?.focus();
		} catch (error) {
			showDialogError('No se pudo hacer la búsqueda rápida. Inténtalo de nuevo en un momento.');
			if (!dialog.open) dialog.showModal();
		}
	}

	// Reservar on the suggestion goes straight to "¡Reservación confirmada!" (Figma), through the usual create route.
	async function reserveSuggestion(form) {
		const button = $('[data-quick-find-reserve]', form);
		const errorBox = $('[data-quick-find-error]', form);
		const body = csrfBody();
		body.set('spot_id', form.dataset.spotId);
		body.set('start_time', form.dataset.start);
		body.set('end_time', form.dataset.end);
		button.disabled = true;
		errorBox.hidden = true;
		try {
			const response = await fetch(`${baseUrl}`, { method: 'POST', body, headers: { Accept: 'application/json' } });
			if (followLoginRedirect(response)) return;
			const data = await response.json().catch(() => ({}));
			if (response.status === 201) {
				state.reserved = true;
				state.holding = false; // reserving ends the user's Quick Find hold
				dialogBody.innerHTML = data.html;
				$('button', dialogBody)?.focus();
				return;
			}
			$('[data-quick-find-error-text]', errorBox).textContent =
				data.message || 'No se pudo guardar la reservación. Inténtalo de nuevo en un momento.';
		} catch (error) {
			$('[data-quick-find-error-text]', errorBox).textContent = 'No se pudo conectar con el servidor. Inténtalo de nuevo.';
		}
		errorBox.hidden = false;
		button.disabled = false;
	}

	dialogBody.addEventListener('submit', (event) => {
		const form = event.target.closest('[data-quick-find-form]');
		if (!form) return;
		event.preventDefault();
		postQuickFind(form.action, new FormData(form));
	});

	// Changing the duration or lot is a new search, so the spots shown so far no longer count.
	dialogBody.addEventListener('change', (event) => {
		if (!event.target.matches('[data-quick-find-field]')) return;
		const form = event.target.closest('[data-quick-find-form]');
		form.elements.skip.value = '';
		postQuickFind(form.action, new FormData(form));
	});

	dialogBody.addEventListener('submit', async (event) => {
		const form = event.target.closest('[data-confirm-form]');
		if (!form) return;
		event.preventDefault();
		const submit = $('[type=submit]', form);
		const errorBox = $('[data-confirm-error]', form);
		submit.disabled = true;
		errorBox.hidden = true;
		try {
			const response = await fetch(form.action, {
				method: 'POST',
				body: new FormData(form),
				headers: { Accept: 'application/json' },
			});
			if (followLoginRedirect(response)) return;
			const data = await response.json().catch(() => ({}));
			if (response.status === 201) {
				state.reserved = true;
				state.holding = false; // reserving ends the user's Quick Find hold
				dialogBody.innerHTML = data.html;
				$('button', dialogBody)?.focus();
				return;
			}
			$('[data-confirm-error-text]', errorBox).textContent =
				data.message || 'No se pudo guardar la reservación. Inténtalo de nuevo en un momento.';
			errorBox.hidden = false;
			// Someone may have just taken the spot, so show the latest availability behind the dialog.
			loadChart();
			loadLots();
		} catch (error) {
			$('[data-confirm-error-text]', errorBox).textContent = 'No se pudo conectar con el servidor. Inténtalo de nuevo.';
			errorBox.hidden = false;
		} finally {
			submit.disabled = false;
		}
	});

	// Clicking the dimmed backdrop closes the dialog, like Esc does.
	dialog.addEventListener('click', (event) => {
		if (event.target === dialog) dialog.close();
	});

	dialog.addEventListener('close', () => {
		dialogBody.innerHTML = '';
		if (state.holding) {
			// Free the suggested spot for others now instead of waiting for the hold to expire.
			state.holding = false;
			const body = new FormData();
			body.set('csrf_token', page.dataset.csrf);
			fetch(page.dataset.releaseUrl, { method: 'POST', body, keepalive: true }).catch(() => {});
		}
		if (state.reserved) {
			state.reserved = false;
			loadChart();
			loadLots();
		}
	});

	showSelection();
})();
