(() => {
	const page = document.querySelector('[data-my-reservations]');
	if (!page) return;

	const CLOSING_HOUR = 22;
	const SLOT_MINUTES = 30;
	const EXTEND_OPTIONS = 4;
	const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
	const NOT_READY = 'Esta acción todavía no está disponible.';
	const GENERIC_ERROR = 'No pudimos completar la acción. Inténtalo de nuevo.';

	const pageError = page.querySelector('[data-page-error]');
	const dialogs = Object.fromEntries(
		[...document.querySelectorAll('[data-dialog]')].map((dialog) => [dialog.dataset.dialog, dialog]),
	);


	async function post(url, body) {
		let response;
		try {
			response = await fetch(url, { method: 'POST', body, headers: { Accept: 'application/json' } });
		} catch {
			throw new Error('No pudimos conectarnos. Revisa tu conexión e inténtalo de nuevo.');
		}
		// The endpoint doesn't exist yet on the backend.
		if (response.status === 404 || response.status === 405) throw new Error(NOT_READY);
		const data = await response.json().catch(() => ({}));
		if (!response.ok) throw new Error(data.message || GENERIC_ERROR);
		return data;
	}

	function showError(dialog, message) {
		const box = dialog.querySelector('[data-error]');
		box.textContent = message;
		box.hidden = !message;
	}

	function setDetails(dialog, rows) {
		const list = dialog.querySelector('[data-details]');
		list.replaceChildren(...rows.flatMap(([label, value]) => {
			const dt = document.createElement('dt');
			dt.className = 'text-[13px] text-ink/60';
			dt.textContent = label;
			const dd = document.createElement('dd');
			dd.className = 'font-semibold';
			dd.textContent = value;
			return [dt, dd];
		}));
	}

	function setText(dialog, selector, text) {
		dialog.querySelector(selector).textContent = text;
	}

	function spotText(info) {
		return info.floor ? `Espacio ${info.spot} · Piso ${info.floor}` : `Espacio ${info.spot}`;
	}

	function formatTime(hours, minutes) {
		const suffix = hours >= 12 ? 'PM' : 'AM';
		const hour12 = hours % 12 || 12;
		return `${hour12}:${String(minutes).padStart(2, '0')} ${suffix}`;
	}

	function open(name, info) {
		const dialog = dialogs[name];
		const form = dialog.querySelector('[data-form]');
		form.reset();
		showError(dialog, '');
		dialog.querySelectorAll('[data-submit]').forEach((button) => { button.disabled = false; });
		dialog.info = info;
		setup[name]?.(dialog, info);
		dialog.showModal();
		return dialog;
	}

	const search = page.querySelector('[data-search]');
	const filterButtons = page.querySelectorAll('[data-filter]');
	const noResults = page.querySelector('[data-no-results]');
	let status = 'all';

	function applyFilters() {
		const query = search.value.trim().toLowerCase();
		let anyVisible = false;
		page.querySelectorAll('[data-section]').forEach((section) => {
			let sectionVisible = false;
			section.querySelectorAll('[data-reservation]').forEach((card) => {
				const show = (status === 'all' || card.dataset.status === status) && card.dataset.search.includes(query);
				card.hidden = !show;
				sectionVisible ||= show;
			});
			section.hidden = !sectionVisible;
			anyVisible ||= sectionVisible;
		});
		noResults.hidden = anyVisible || !page.querySelector('[data-reservation]');
	}

	search.addEventListener('input', applyFilters);
	filterButtons.forEach((button) => {
		button.addEventListener('click', () => {
			status = button.dataset.filter;
			filterButtons.forEach((other) => other.setAttribute('aria-checked', String(other === button)));
			applyFilters();
		});
	});

	const setup = {
		cancel(dialog, info) {
			setText(dialog, '[data-title]', '¿Cancelar esta reservación?');
			setText(dialog, '[data-subtitle]', '¿Seguro que quieres cancelarla? El espacio se libera enseguida y te llegará un correo de cancelación.');
			setDetails(dialog, [['Lote', info.lot], ['Espacio', spotText(info)], ['Cuándo', `${info.date} · ${info.start} – ${info.end}`]]);
		},

		checkout(dialog, info) {
			setText(dialog, '[data-title]', `¿Check out de ${info.lot}?`);
			setText(dialog, '[data-subtitle]', `Tu reservación dura hasta las ${info.end}. Si haces check out ahora, el espacio ${info.spot} queda libre para otras personas.`);
			setDetails(dialog, [['Espacio', spotText(info)], ['Comenzó', `Hoy, ${info.start}`], ['Termina', `Hoy, ${info.end}`]]);
			setText(dialog, '[data-extend-hint]', `Si el espacio ${info.spot} está libre después de las ${info.end}, puedes extender tu reservación.`);

			const select = dialog.querySelector('[data-extend-select]');
			const [endHours, endMinutes] = info.end_time.split(':').map(Number);
			const options = [];
			for (let step = 1; step <= EXTEND_OPTIONS; step += 1) {
				const total = endHours * 60 + endMinutes + step * SLOT_MINUTES;
				if (total > CLOSING_HOUR * 60) break;
				const hours = Math.floor(total / 60);
				const minutes = total % 60;
				const option = new Option(formatTime(hours, minutes), `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`);
				options.push(option);
			}
			select.replaceChildren(...options);
			const canExtend = options.length > 0;
			select.disabled = !canExtend;
			dialog.querySelector('[data-extend]').disabled = !canExtend;
			if (!canExtend) setText(dialog, '[data-extend-hint]', 'El lote cierra a esta hora, así que no se puede extender.');
		},

		incident(dialog, info) {
			setText(dialog, '[data-subtitle]', `${info.lot} · ${info.spot} · Hoy ${info.start} – ${info.end}`);
			setText(dialog, '[data-photo-label]', 'Haz clic para subir o arrastra una foto aquí');
		},
	};


	page.addEventListener('click', async (event) => {
		const card = event.target.closest('[data-reservation]');
		if (!card) return;
		const info = JSON.parse(card.dataset.info);

		const opener = event.target.closest('[data-open]');
		if (opener) {
			open(opener.dataset.open, info);
			return;
		}

		const checkIn = event.target.closest('[data-check-in]');
		if (checkIn) {
			checkIn.disabled = true;
			pageError.hidden = true;
			try {
				await post(info.urls.check_in, new FormData(dialogs.cancel.querySelector('[data-form]')));
				window.location.reload();
			} catch (error) {
				pageError.textContent = error.message;
				pageError.hidden = false;
				checkIn.disabled = false;
			}
		}
	});

	Object.values(dialogs).forEach((dialog) => {
		dialog.addEventListener('click', (event) => {
			if (event.target === dialog || event.target.closest('[data-close-dialog]')) {
				dialog.close();
				if (event.target.closest('[data-reload]')) window.location.reload();
			}
		});
	});

	// Submitting 

	async function submitDialog(dialog, button, action) {
		button.disabled = true;
		showError(dialog, '');
		try {
			await action();
		} catch (error) {
			showError(dialog, error.message);
			button.disabled = false;
		}
	}

	dialogs.cancel.querySelector('[data-form]').addEventListener('submit', (event) => {
		event.preventDefault();
		const dialog = dialogs.cancel;
		submitDialog(dialog, dialog.querySelector('[data-submit]'), async () => {
			await post(dialog.info.urls.cancel, new FormData(event.target));
			window.location.reload();
		});
	});

	dialogs.checkout.querySelector('[data-form]').addEventListener('submit', (event) => {
		event.preventDefault();
		const dialog = dialogs.checkout;
		submitDialog(dialog, dialog.querySelector('[data-submit]'), async () => {
			const body = new FormData(event.target);
			body.delete('end_time');
			await post(dialog.info.urls.check_out, body);
			window.location.reload();
		});
	});

	dialogs.checkout.querySelector('[data-extend]').addEventListener('click', (event) => {
		const dialog = dialogs.checkout;
		submitDialog(dialog, event.currentTarget, async () => {
			await post(dialog.info.urls.extend, new FormData(dialog.querySelector('[data-form]')));
			window.location.reload();
		});
	});

	// Incident 

	const incidentForm = dialogs.incident.querySelector('[data-form]');
	const photoInput = incidentForm.querySelector('[data-photo]');
	const dropzone = incidentForm.querySelector('[data-dropzone]');

	function showPhotoName() {
		const file = photoInput.files[0];
		setText(dialogs.incident, '[data-photo-label]', file ? file.name : 'Haz clic para subir o arrastra una foto aquí');
	}

	photoInput.addEventListener('change', showPhotoName);
	dropzone.addEventListener('dragover', (event) => {
		event.preventDefault();
		dropzone.classList.add('border-brand');
	});
	dropzone.addEventListener('dragleave', () => dropzone.classList.remove('border-brand'));
	dropzone.addEventListener('drop', (event) => {
		event.preventDefault();
		dropzone.classList.remove('border-brand');
		if (event.dataTransfer.files.length) {
			photoInput.files = event.dataTransfer.files;
			showPhotoName();
		}
	});

	function incidentProblem(form) {
		const type = form.incident_type.value;
		const description = form.description.value.trim();
		const photo = photoInput.files[0];
		if (photo && !['image/jpeg', 'image/png'].includes(photo.type)) return 'La foto debe ser JPG o PNG.';
		if (photo && photo.size > MAX_PHOTO_BYTES) return 'La foto no puede pasar de 5 MB.';
		if (!description && (type === 'Other' || !photo)) return 'Describe lo que pasó o añade una foto.';
		return null;
	}

	incidentForm.addEventListener('submit', (event) => {
		event.preventDefault();
		const dialog = dialogs.incident;
		const problem = incidentProblem(incidentForm);
		if (problem) {
			showError(dialog, problem);
			return;
		}
		submitDialog(dialog, dialog.querySelector('[data-submit]'), async () => {
			const result = await post(dialog.info.urls.incident, new FormData(incidentForm));
			dialog.close();
			showIncidentResult(dialog.info, result);
		});
	});

	//  result and replacement 

	function showIncidentResult(info, result) {
		const dialog = open('incident-result', info);
		const replacement = result.replacement || null;
		dialog.replacement = replacement;

		setText(dialog, '[data-title]', result.report_id ? `Reporte #${result.report_id} enviado` : 'Reporte enviado');
		setText(dialog, '[data-subtitle]', replacement
			? 'Le avisamos a administración. También encontramos un espacio de reemplazo para el resto de tu reservación:'
			: 'Le avisamos a administración y van a revisar tu reporte.');

		dialog.querySelector('[data-replacement]').hidden = !replacement;
		dialog.querySelector('[data-replacement-note]').hidden = !replacement;
		dialog.querySelector('[data-no-replacement]').hidden = Boolean(replacement);
		dialog.querySelector('[data-replacement-only]').hidden = !replacement;
		dialog.querySelector('[data-no-replacement-only]').hidden = Boolean(replacement);
		const close = dialog.querySelector('[data-close-dialog][data-reload]');
		close.textContent = replacement ? close.dataset.labelReplacement : close.dataset.labelNone;

		if (replacement) {
			setText(dialog, '[data-replacement-title]', `${replacement.lot} · Espacio ${replacement.spot}`);
			const floor = replacement.floor ? `Piso ${replacement.floor} · ` : '';
			setText(dialog, '[data-replacement-detail]', `${floor}Ahora – ${replacement.end || info.end} (el tiempo que te queda)`);
		}
	}

	dialogs['incident-result'].querySelector('[data-form]').addEventListener('submit', (event) => {
		event.preventDefault();
		const dialog = dialogs['incident-result'];
		if (!dialog.replacement) return;
		submitDialog(dialog, dialog.querySelector('[data-submit]'), async () => {
			const url = dialog.replacement.accept_url;
			if (!url) throw new Error(NOT_READY);
			await post(url, new FormData(event.target));
			window.location.reload();
		});
	});
})();
