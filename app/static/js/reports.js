// Lot usage reports (SRS REQ.2.4, SDS Screen #3). Styling lives in the template;
// this file fills it in with the report data and draws the frequency chart with D3.
(() => {
	const $ = (selector, root = document) => root.querySelector(selector);
	const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

	const page = $('[data-reports-page]');
	if (!page) return;

	const reportUrl = page.dataset.reportUrl;
	const subtitle = $('[data-report-subtitle]', page);
	const errorBox = $('[data-report-error]', page);
	const lotPicker = $('[data-lot-picker]', page);
	const lotInput = $('[data-lot-input]', page);
	const lotToggle = $('[data-lot-toggle]', page);
	const lotList = $('[data-lot-options]', page);
	const lotOptions = $$('[role="option"]', lotList);
	const lotEmpty = $('[data-lot-empty]', lotList);
	const periodButtons = $$('[data-period]', page);
	const roleButtons = $$('[data-role]', page);
	const rankingList = $('[data-ranking]', page);
	const rankingEmpty = $('[data-ranking-empty]', page);
	const rankingHint = $('[data-ranking-hint]', page);
	const rowTemplate = $('[data-rank-row-template]', page);
	const chartHolder = $('[data-frequency-chart]', page);
	const chartEmpty = $('[data-frequency-empty]', page);
	const chartScope = $('[data-chart-scope]', page);
	const chartCaption = $('[data-chart-caption]', page);
	const tooltip = $('[data-chart-tooltip]', page);

	const PERIODS = ['today', 'week'];
	const params = new URLSearchParams(window.location.search);
	const state = {
		period: PERIODS.includes(params.get('period')) ? params.get('period') : 'today',
		lot: lotOptions.some((option) => option.dataset.value === params.get('lot')) ? params.get('lot') : '',
		role: roleButtons.some((button) => button.dataset.role === params.get('role')) ? params.get('role') : '',
	};
	let report = null;
	let controller = null;

	// ------------------------------------------------------------------ Formatting
	const integer = new Intl.NumberFormat('es-PR');
	const longDate = new Intl.DateTimeFormat('es-PR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
	const shortDate = new Intl.DateTimeFormat('es-PR', { weekday: 'short', day: 'numeric', month: 'short' });
	const dateRange = new Intl.DateTimeFormat('es-PR', { day: 'numeric', month: 'long', year: 'numeric' });

	const isNumber = (value) => typeof value === 'number' && Number.isFinite(value);
	const clamp = (value) => (isNumber(value) ? Math.min(Math.max(value, 0), 1) : 0);
	const percent = (value) => (isNumber(value) ? `${Math.round(value * 100)}%` : null);
	const plural = (count, one, many) => `${integer.format(count)} ${count === 1 ? one : many}`;

	// Times come as 'HH:MM' or 'YYYY-MM-DDTHH:MM', in Puerto Rico time.
	function parseTime(value) {
		const time = value.includes('T') ? value.split('T')[1] : value;
		const [hours, minutes] = time.split(':').map(Number);
		return { hours, minutes };
	}

	const meridiem = ({ hours }) => (hours < 12 ? 'AM' : 'PM');
	const clock = ({ hours, minutes }) => `${hours % 12 || 12}:${String(minutes).padStart(2, '0')}`;

	function formatTime(value) {
		const time = parseTime(value);
		return `${clock(time)} ${meridiem(time)}`;
	}

	// Axis labels drop ':00', like '6 AM'.
	function formatAxisTime(value) {
		const time = parseTime(value);
		return time.minutes === 0 ? `${time.hours % 12 || 12} ${meridiem(time)}` : formatTime(value);
	}

	function formatTimeRange(start, end) {
		const from = parseTime(start);
		const to = parseTime(end);
		return meridiem(from) === meridiem(to)
			? `${clock(from)} – ${clock(to)} ${meridiem(to)}`
			: `${formatTime(start)} – ${formatTime(end)}`;
	}

	// 'YYYY-MM-DD' read as a local date, so the day doesn't shift with the browser's time zone.
	function parseDate(value) {
		const [year, month, day] = value.slice(0, 10).split('-').map(Number);
		return new Date(year, month - 1, day);
	}

	function normalize(text) {
		return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
	}

	// ------------------------------------------------------------------ Data
	function followLoginRedirect(response) {
		if (response.redirected) window.location.assign(response.url);
		return response.redirected;
	}

	function query() {
		const query = new URLSearchParams({ period: state.period });
		if (state.lot) query.set('lot', state.lot);
		if (state.role) query.set('role', state.role);
		return query;
	}

	function syncUrl() {
		const url = new URL(window.location.href);
		url.search = query().toString();
		window.history.replaceState(null, '', url);
	}

	async function load() {
		controller?.abort();
		const current = new AbortController();
		controller = current;
		page.setAttribute('aria-busy', 'true');
		errorBox.hidden = true;
		syncControls();
		syncUrl();
		try {
			const response = await fetch(`${reportUrl}?${query()}`, {
				headers: { Accept: 'application/json' },
				signal: current.signal,
			});
			if (followLoginRedirect(response)) return;
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			report = await response.json();
			render();
		} catch (error) {
			if (error.name === 'AbortError') return;
			errorBox.hidden = false;
			if (!report) renderUnavailable();
		} finally {
			if (controller === current) page.removeAttribute('aria-busy');
		}
	}

	// ------------------------------------------------------------------ Filters
	const selectedOption = () => lotOptions.find((option) => option.dataset.value === state.lot) ?? lotOptions[0];
	const selectedRole = () => roleButtons.find((button) => button.dataset.role === state.role) ?? roleButtons[0];

	function syncControls() {
		periodButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.period === state.period)));
		roleButtons.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.role === state.role)));
		lotOptions.forEach((option) => option.setAttribute('aria-selected', String(option.dataset.value === state.lot)));
		if (document.activeElement !== lotInput) lotInput.value = state.lot ? selectedOption().dataset.label : '';
	}

	function setPeriod(period) {
		if (period === state.period) return;
		state.period = period;
		load();
	}

	function setRole(role) {
		if (role === state.role) return;
		state.role = role;
		load();
	}

	function setLot(lot) {
		closeLotList();
		if (lot === state.lot) {
			syncControls();
			return;
		}
		state.lot = lot;
		lotInput.value = lot ? selectedOption().dataset.label : '';
		load();
	}

	// ------------------------------------------------------------------ Lot combobox
	let activeIndex = -1;
	const visibleOptions = () => lotOptions.filter((option) => !option.hidden);

	function setActiveOption(index) {
		const options = visibleOptions();
		activeIndex = index;
		options.forEach((option, position) => option.toggleAttribute('data-active', position === index));
		const active = options[index];
		if (active) {
			lotInput.setAttribute('aria-activedescendant', active.id);
			active.scrollIntoView({ block: 'nearest' });
		} else {
			lotInput.removeAttribute('aria-activedescendant');
		}
	}

	function filterLotOptions(text) {
		const search = normalize(text);
		lotOptions.forEach((option) => {
			option.hidden = Boolean(search) && option.dataset.value !== '' && !normalize(option.dataset.search).includes(search);
		});
		lotEmpty.hidden = visibleOptions().length > 1;
	}

	function openLotList() {
		if (!lotList.hidden) return;
		lotList.hidden = false;
		lotInput.setAttribute('aria-expanded', 'true');
		const options = visibleOptions();
		setActiveOption(Math.max(options.findIndex((option) => option.dataset.value === state.lot), 0));
	}

	function closeLotList() {
		lotList.hidden = true;
		lotInput.setAttribute('aria-expanded', 'false');
		setActiveOption(-1);
		filterLotOptions('');
	}

	lotInput.addEventListener('focus', () => lotInput.select());
	lotInput.addEventListener('click', openLotList);
	lotInput.addEventListener('input', () => {
		filterLotOptions(lotInput.value);
		openLotList();
		setActiveOption(lotInput.value.trim() && visibleOptions().length > 1 ? 1 : 0);
	});
	lotInput.addEventListener('keydown', (event) => {
		const options = visibleOptions();
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (lotList.hidden) {
				openLotList();
				return;
			}
			const step = event.key === 'ArrowDown' ? 1 : -1;
			setActiveOption((activeIndex + step + options.length) % options.length);
		} else if (event.key === 'Enter') {
			if (lotList.hidden || !options[activeIndex]) return;
			event.preventDefault();
			setLot(options[activeIndex].dataset.value);
		} else if (event.key === 'Escape') {
			if (lotList.hidden) return;
			event.preventDefault();
			closeLotList();
			syncControls();
		}
	});
	lotToggle.addEventListener('click', () => {
		if (lotList.hidden) {
			lotInput.focus();
			openLotList();
		} else {
			closeLotList();
		}
	});
	// mousedown keeps the focus in the input, so focusout doesn't close the list before the click.
	lotList.addEventListener('mousedown', (event) => event.preventDefault());
	lotList.addEventListener('click', (event) => {
		const option = event.target.closest('[role="option"]');
		if (option) setLot(option.dataset.value);
	});
	lotPicker.addEventListener('focusout', (event) => {
		if (lotPicker.contains(event.relatedTarget)) return;
		closeLotList();
		lotInput.value = state.lot ? selectedOption().dataset.label : '';
	});

	periodButtons.forEach((button) => button.addEventListener('click', () => setPeriod(button.dataset.period)));
	roleButtons.forEach((button) => button.addEventListener('click', () => setRole(button.dataset.role)));
	$('[data-report-retry]', page).addEventListener('click', load);

	// ------------------------------------------------------------------ Render
	function scopeLabel() {
		return state.lot ? selectedOption().dataset.label : 'todos los lotes';
	}

	function renderSubtitle() {
		const parts = [`Uso en ${scopeLabel()}`];
		const roleScope = selectedRole().dataset.scopeLabel;
		if (roleScope) parts[0] += ` · solo ${roleScope}`;
		const range = report?.range;
		if (range?.start && range?.end) {
			const period = state.period === 'today'
				? `Hoy, ${longDate.format(parseDate(range.end))}`
				: `Últimos 7 días, ${dateRange.formatRange(parseDate(range.start), parseDate(range.end))}`;
			parts.push(report.generated_at ? `${period} (actualizado ${formatTime(report.generated_at)})` : period);
		}
		subtitle.textContent = parts.join(' · ');
	}

	function setMetric(name, value, detail) {
		const card = $(`[data-metric="${name}"]`, page);
		const valueElement = $('[data-metric-value]', card);
		valueElement.textContent = value ?? '—';
		valueElement.title = value ?? '';
		$('[data-metric-detail]', card).textContent = detail ?? 'Sin datos';
	}

	function renderMetrics() {
		const summary = report?.summary ?? {};

		setMetric(
			'reservations',
			isNumber(summary.total_reservations) ? integer.format(summary.total_reservations) : null,
			isNumber(summary.active_lots) ? `En ${plural(summary.active_lots, 'lote activo', 'lotes activos')}` : null,
		);
		setMetric(
			'occupancy',
			percent(summary.average_occupancy),
			isNumber(summary.active_spots) ? `De ${plural(summary.active_spots, 'espacio activo', 'espacios activos')}` : null,
		);

		const peak = summary.peak;
		const peakDetail = peak
			? [
				state.period === 'week' && peak.start ? shortDate.format(parseDate(peak.start)) : null,
				isNumber(peak.occupancy) ? `${percent(peak.occupancy)} de los espacios en uso` : null,
			].filter(Boolean).join(' · ')
			: '';
		setMetric(
			'peak',
			peak?.start && peak?.end ? formatTimeRange(peak.start, peak.end) : null,
			peakDetail || (isNumber(summary.total_reservations) && summary.total_reservations === 0 ? 'Sin reservaciones' : null),
		);

		setMetric(
			'accessible',
			percent(summary.accessible_occupancy),
			isNumber(summary.accessible_reserved) && isNumber(summary.accessible_spots)
				? `${integer.format(summary.accessible_reserved)} de ${plural(summary.accessible_spots, 'espacio accesible', 'espacios accesibles')}`
				: null,
		);

		const incidents = summary.incidents;
		setMetric(
			'incidents',
			isNumber(incidents?.total) ? integer.format(incidents.total) : null,
			isNumber(incidents?.pending) && isNumber(incidents?.resolved)
				? `${plural(incidents.pending, 'pendiente', 'pendientes')} · ${plural(incidents.resolved, 'resuelto', 'resueltos')}`
				: null,
		);
	}

	function renderRanking() {
		const rows = Array.isArray(report?.ranking) ? report.ranking : [];
		const selectable = state.lot === '';
		let rank = 0;

		rankingList.replaceChildren(...rows.map((lot) => {
			const row = rowTemplate.content.firstElementChild.cloneNode(true);
			const button = $('[data-rank-button]', row);
			const active = lot.is_active !== false;
			if (active) rank += 1;
			const occupancy = clamp(lot.occupancy);

			button.dataset.active = String(active);
			button.dataset.top = String(active && rank === 1);
			$('[data-rank]', row).textContent = active ? `#${rank}` : '—';
			$('[data-rank-name]', row).textContent = lot.name ?? '';
			$('[data-rank-location]', row).textContent = lot.location ?? '';
			$('[data-rank-inactive]', row).hidden = active;
			$('[data-rank-bar]', row).style.width = `${occupancy * 100}%`;
			$('[data-rank-meter]', row).setAttribute('aria-valuenow', String(Math.round(occupancy * 100)));
			$('[data-rank-count]', row).textContent = `${integer.format(lot.reserved ?? 0)}/${integer.format(lot.capacity ?? 0)}`;

			const lotId = lot.id == null ? '' : String(lot.id);
			if (selectable && lotOptions.some((option) => option.dataset.value === lotId && lotId !== '')) {
				button.dataset.lotId = lotId;
			} else {
				button.disabled = true;
			}
			return row;
		}));

		rankingEmpty.hidden = rows.length > 0;
		rankingHint.textContent = selectable
			? 'Por ocupación promedio. Selecciona un lote para ver su reporte.'
			: 'Por ocupación promedio.';
	}

	rankingList.addEventListener('click', (event) => {
		const button = event.target.closest('[data-rank-button]');
		if (!button?.dataset.lotId) return;
		setLot(button.dataset.lotId);
		page.scrollIntoView({ behavior: 'smooth', block: 'start' });
	});

	function renderCaption(total) {
		chartScope.textContent = scopeLabel();
		const minutes = report?.frequency?.slot_minutes;
		const slot = isNumber(minutes) ? `cada intervalo de ${minutes} minutos` : 'cada intervalo';
		const when = state.period === 'today' ? 'hoy' : 'en los últimos 7 días, sumando cada día';
		chartCaption.textContent = `Reservaciones que empiezan en ${slot} ${when} (${integer.format(total)} en total)`;
	}

	function render() {
		renderSubtitle();
		renderMetrics();
		renderRanking();
		drawChart();
	}

	function renderUnavailable() {
		subtitle.textContent = `Uso en ${scopeLabel()}`;
		['reservations', 'occupancy', 'peak', 'accessible', 'incidents'].forEach((name) => setMetric(name, null, null));
		rankingList.replaceChildren();
		rankingEmpty.hidden = true;
		chartHolder.replaceChildren();
		chartEmpty.hidden = true;
		tooltip.hidden = true;
	}

	// ------------------------------------------------------------------ Frequency chart
	const CHART_HEIGHT = 320;
	const MARGIN = { top: 30, right: 12, bottom: 28, left: 34 };
	const MIN_LABEL_GAP = 46;

	function showTooltip(slot, x, y, bars) {
		bars.classed('active', (other) => other === slot);
		tooltip.textContent = `${formatTime(slot.start)} · ${integer.format(slot.count)}`;
		tooltip.style.left = `${x}px`;
		tooltip.style.top = `${y - 6}px`;
		tooltip.hidden = false;
	}

	function drawChart() {
		const slots = (Array.isArray(report?.frequency?.slots) ? report.frequency.slots : [])
			.filter((slot) => typeof slot?.start === 'string')
			.map((slot) => ({ start: slot.start, count: isNumber(slot.count) ? slot.count : 0 }));
		const total = slots.reduce((sum, slot) => sum + slot.count, 0);

		renderCaption(total);
		chartHolder.replaceChildren();
		tooltip.hidden = true;
		chartEmpty.hidden = total > 0;
		if (!slots.length || !window.d3) return;

		const { d3 } = window;
		const width = chartHolder.clientWidth;
		const max = d3.max(slots, (slot) => slot.count) ?? 0;
		const x = d3.scaleBand()
			.domain(slots.map((slot) => slot.start))
			.range([MARGIN.left, width - MARGIN.right])
			.paddingInner(0.25);
		const y = d3.scaleLinear()
			.domain([0, Math.max(max, 4)])
			.nice(4)
			.range([CHART_HEIGHT - MARGIN.bottom, MARGIN.top]);
		const peak = max > 0 ? slots.find((slot) => slot.count === max) : null;

		const svg = d3.select(chartHolder)
			.append('svg')
			.attr('width', width)
			.attr('height', CHART_HEIGHT)
			.attr('viewBox', `0 0 ${width} ${CHART_HEIGHT}`)
			.attr('role', 'img')
			.attr('aria-label', peak
				? `${chartCaption.textContent}. El intervalo con más reservaciones empieza a las ${formatTime(peak.start)}, con ${integer.format(peak.count)}.`
				: chartCaption.textContent);

		const ticks = y.ticks(4);
		svg.append('g')
			.selectAll('line')
			.data(ticks)
			.join('line')
			.attr('class', 'grid')
			.attr('x1', MARGIN.left)
			.attr('x2', width - MARGIN.right)
			.attr('y1', (tick) => y(tick))
			.attr('y2', (tick) => y(tick));
		svg.append('g')
			.selectAll('text')
			.data(ticks)
			.join('text')
			.attr('class', 'axis')
			.attr('x', MARGIN.left - 8)
			.attr('y', (tick) => y(tick))
			.attr('dy', '0.32em')
			.attr('text-anchor', 'end')
			.text((tick) => integer.format(tick));

		// Label the first slot, every 6 hours and the last slot, skipping any that would overlap.
		const center = (slot) => x(slot.start) + x.bandwidth() / 2;
		const labels = [];
		slots.forEach((slot, index) => {
			const { hours, minutes } = parseTime(slot.start);
			const last = index === slots.length - 1;
			if (!(index === 0 || last || (minutes === 0 && hours % 6 === 0))) return;
			const previous = labels[labels.length - 1];
			if (previous && center(slot) - center(previous) < MIN_LABEL_GAP) {
				if (!last) return;
				labels.pop();
			}
			labels.push(slot);
		});
		svg.append('g')
			.selectAll('text')
			.data(labels)
			.join('text')
			.attr('class', 'axis')
			.attr('x', center)
			.attr('y', CHART_HEIGHT - 6)
			.attr('text-anchor', (slot, index) => (index === 0 ? 'start' : index === labels.length - 1 ? 'end' : 'middle'))
			.attr('dx', (slot, index) => (index === 0 ? -x.bandwidth() / 2 : index === labels.length - 1 ? x.bandwidth() / 2 : 0))
			.text((slot) => formatAxisTime(slot.start));

		const bars = svg.append('g')
			.selectAll('rect')
			.data(slots)
			.join('rect')
			.attr('class', 'bar')
			.attr('x', (slot) => x(slot.start))
			.attr('width', x.bandwidth())
			.attr('y', (slot) => y(slot.count))
			.attr('height', (slot) => y(0) - y(slot.count));

		drawNowMarker(svg, slots, x);

		const showPeak = () => {
			if (peak) showTooltip(peak, center(peak), y(peak.count), bars);
			else {
				tooltip.hidden = true;
				bars.classed('active', false);
			}
		};

		// Full-height hit areas, so short bars are easy to hover.
		svg.append('g')
			.selectAll('rect')
			.data(slots)
			.join('rect')
			.attr('class', 'hit')
			.attr('x', (slot) => x(slot.start) - (x.step() - x.bandwidth()) / 2)
			.attr('width', x.step())
			.attr('y', MARGIN.top)
			.attr('height', y(0) - MARGIN.top)
			.on('pointerenter', (event, slot) => showTooltip(slot, center(slot), y(slot.count), bars))
			.on('pointerleave', showPeak);

		showPeak();
	}

	// Today's chart marks the time the report was generated.
	function drawNowMarker(svg, slots, x) {
		if (state.period !== 'today' || !report?.generated_at) return;
		const minutesOf = (value) => {
			const { hours, minutes } = parseTime(value);
			return hours * 60 + minutes;
		};
		const slotMinutes = isNumber(report.frequency?.slot_minutes)
			? report.frequency.slot_minutes
			: slots.length > 1 ? minutesOf(slots[1].start) - minutesOf(slots[0].start) : 30;
		const now = minutesOf(report.generated_at);
		const slot = slots.find((candidate) => {
			const start = minutesOf(candidate.start);
			return now >= start && now < start + slotMinutes;
		});
		if (!slot) return;

		const position = x(slot.start) + x.step() * ((now - minutesOf(slot.start)) / slotMinutes);
		const width = Number(svg.attr('width'));
		svg.append('line')
			.attr('class', 'now-line')
			.attr('x1', position)
			.attr('x2', position)
			.attr('y1', MARGIN.top - 8)
			.attr('y2', CHART_HEIGHT - MARGIN.bottom)
			.attr('stroke-dasharray', '3 3');
		svg.append('text')
			.attr('class', 'now-label')
			.attr('x', position + (position > width / 2 ? -6 : 6))
			.attr('y', MARGIN.top - 12)
			.attr('text-anchor', position > width / 2 ? 'end' : 'start')
			.text(`Ahora ${formatTime(report.generated_at)}`);
	}

	let lastWidth = chartHolder.clientWidth;
	new ResizeObserver(() => {
		const width = chartHolder.clientWidth;
		if (width === lastWidth || !report) return;
		lastWidth = width;
		window.requestAnimationFrame(drawChart);
	}).observe(chartHolder);

	load();
})();
