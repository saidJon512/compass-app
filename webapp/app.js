/* ══════════════════════════════════════════════════════════════════
   Telegram Mini App — mijoz tomoni

   Bu fayl FAQAT ko'rsatadi. To'g'ri javoblar, daraja qarori va sessiya
   holati — hammasi serverda. Shuning uchun bu koddagi hech narsani
   o'zgartirib natijani soxtalashtirib bo'lmaydi.
   ══════════════════════════════════════════════════════════════════ */

'use strict';

const tg = window.Telegram?.WebApp;

// style.css dagi --bg bilan bir xil bo'lishi shart.
const APP_BG = '#0A0A0B';

// A1/A2/… — faqat ichki kalitlar, ular ekranda HECH QACHON ko'rsatilmaydi.
// Zinapoyada qisqartma, boshqa hamma joyda to'liq nom ishlatiladi.
const LADDER = [
  { code: 'A1', short: 'Beg',     name: 'Beginner' },
  { code: 'A2', short: 'Elem',    name: 'Elementary' },
  { code: 'B1', short: 'Pre-Int', name: 'Pre-Intermediate' },
  { code: 'B2', short: 'Int',     name: 'Intermediate' },
  { code: 'C1', short: 'Upp-Int', name: 'Upper-Intermediate' },
  { code: 'C2', short: 'Adv',     name: 'Advanced' },
];

const LEVELS = LADDER.map((l) => l.code);

const $ = (id) => document.getElementById(id);

/* ── Telegram muhiti ───────────────────────────────────────────── */

function initTelegram() {
  if (!tg) return;
  tg.ready();
  tg.expand();

  // Test paytida tasodifiy pastga surish ilovani yopib yubormasin.
  tg.disableVerticalSwipes?.();

  // Telegramning o'z sarlavha satri ham qora bo'lsin — ilova bilan
  // qo'shilib ketsin. Hex ranglar Bot API 6.9 dan qo'llab-quvvatlanadi,
  // eski versiyalarda kalit so'zga qaytamiz.
  try {
    tg.setHeaderColor?.(APP_BG);
    tg.setBackgroundColor?.(APP_BG);
    tg.setBottomBarColor?.(APP_BG);
  } catch {
    try {
      tg.setHeaderColor?.('bg_color');
      tg.setBackgroundColor?.('bg_color');
    } catch { /* juda eski versiya — muhim emas */ }
  }

  tg.BackButton?.onClick(onBack);
}

function haptic(style) {
  try {
    if (style === 'ok')     tg?.HapticFeedback?.notificationOccurred('success');
    else if (style === 'up') tg?.HapticFeedback?.notificationOccurred('warning');
    else                     tg?.HapticFeedback?.impactOccurred(style || 'light');
  } catch { /* qo'llab-quvvatlanmasa — jim o'tamiz */ }
}

function confirmExit(message) {
  return new Promise((resolve) => {
    if (tg?.showConfirm) tg.showConfirm(message, resolve);
    else resolve(window.confirm(message));
  });
}

/* ── Holat ─────────────────────────────────────────────────────── */

const state = {
  screen: 'splash',
  sessionId: null,
  question: null,
  progress: null,
  lastResult: null,
  active: null,
  name: '',
  busy: false,
  picked: null,
};

/* ── Server bilan aloqa ────────────────────────────────────────── */

async function api(path, body = {}) {
  const resp = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, init_data: tg?.initData || '' }),
  });

  if (!resp.ok) {
    let detail = `Server xatosi (${resp.status})`;
    try { detail = (await resp.json()).detail || detail; } catch { /* JSON emas */ }
    throw new Error(detail);
  }
  return resp.json();
}

/* ── Ekranlar ──────────────────────────────────────────────────── */

function show(name) {
  state.screen = name;
  for (const el of document.querySelectorAll('.screen')) {
    el.classList.remove('is-active', 'is-entering');
  }
  const el = $(`screen-${name}`);
  el.classList.add('is-active', 'is-entering');
  $('quiz-scroll').scrollTop = 0;

  // Orqaga tugmasi faqat test davomida kerak.
  if (name === 'quiz') tg?.BackButton?.show();
  else tg?.BackButton?.hide();

  // Test yarmida tasodifan yopilmasin.
  if (name === 'quiz') tg?.enableClosingConfirmation?.();
  else tg?.disableClosingConfirmation?.();
}

function fail(message) {
  $('error-text').textContent = message;
  show('error');
}

async function onBack() {
  if (state.screen !== 'quiz') return;
  const ok = await confirmExit(
    'Testdan chiqasizmi? Javoblaringiz saqlanadi — keyin shu joydan davom ettirasiz.'
  );
  if (ok) {
    haptic('light');
    await openHome();
  }
}

/* ── Daraja zinapoyasi ─────────────────────────────────────────── */

function renderLadder(container, currentLevel, { markDone = true } = {}) {
  const currentIdx = LEVELS.indexOf(currentLevel);
  container.innerHTML = '';
  LADDER.forEach((lvl, i) => {
    const step = document.createElement('div');
    step.className = 'step';
    if (i === currentIdx) step.classList.add('is-current');
    else if (markDone && i < currentIdx) step.classList.add('is-done');
    step.textContent = lvl.short;
    step.title = lvl.name;
    container.append(step);
  });
}

function renderDots(progress) {
  const box = $('block-dots');
  box.innerHTML = '';
  for (let i = 1; i <= progress.block_size; i++) {
    const dot = document.createElement('div');
    dot.className = 'dot';
    if (i < progress.in_block) dot.classList.add('is-answered');
    else if (i === progress.in_block) dot.classList.add('is-current');
    box.append(dot);
  }
}

/* ── Savolni chizish ───────────────────────────────────────────── */

const SKILL_UZ = {
  grammar: 'Grammatika',
  vocabulary: "So'z boyligi",
  reading: "O'qib tushunish",
  writing: 'Yozish',
};

function renderQuestion(question, progress) {
  state.question = question;
  state.progress = progress;
  state.picked = null;

  renderLadder($('quiz-ladder'), progress.level);
  renderDots(progress);

  $('skill-tag').textContent = SKILL_UZ[question.skill] || question.skill;
  $('qcount').textContent = progress.level_name;

  const passage = $('passage');
  passage.classList.toggle('hidden', !question.passage);
  if (question.passage) passage.textContent = question.passage;

  // Topshiriq o'zbekcha, tekshiriladigan jumla esa inglizcha —
  // ularni turlicha ko'rsatamiz, chunki bu ikki xil narsa.
  $('question').textContent = question.question;

  const sentence = $('sentence');
  sentence.classList.toggle('hidden', !question.sentence);
  if (question.sentence) sentence.textContent = question.sentence;

  const isFree = question.type === 'free_text';
  $('options').classList.toggle('hidden', isFree);
  $('free-wrap').classList.toggle('hidden', !isFree);

  if (isFree) renderFreeText(question);
  else renderOptions(question);

  setSubmit(false, 'Davom etish');
}

function renderOptions(question) {
  const box = $('options');
  box.innerHTML = '';

  question.options.forEach((text) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'option';
    btn.innerHTML = '<span class="mark"></span>';

    const label = document.createElement('span');
    label.textContent = text;
    btn.append(label);

    btn.addEventListener('click', () => {
      if (state.busy) return;
      haptic('light');
      state.picked = text;
      for (const el of box.children) el.classList.remove('is-picked');
      btn.classList.add('is-picked');
      setSubmit(true, 'Davom etish');
    });

    box.append(btn);
  });
}

function renderFreeText(question) {
  const area = $('free-text');
  const min = question.min_words || 20;
  area.value = '';

  const update = () => {
    const words = area.value.trim().split(/\s+/).filter(Boolean).length;
    $('word-count').textContent = `${words} / ${min} so'z`;
    setSubmit(words >= min, 'Javobni yuborish');
  };

  area.oninput = update;
  update();
}

function setSubmit(enabled, label) {
  const btn = $('submit-btn');
  btn.disabled = !enabled;
  btn.textContent = label;
}

/* ── Javob yuborish ────────────────────────────────────────────── */

async function submitAnswer() {
  if (state.busy) return;

  const isFree = state.question.type === 'free_text';
  const answer = isFree ? $('free-text').value.trim() : state.picked;
  if (!answer) return;

  state.busy = true;
  const btn = $('submit-btn');
  btn.classList.add('is-busy');
  // Yozma javobni Claude baholaydi — bu bir necha soniya olishi mumkin.
  btn.textContent = isFree ? 'Tekshirilmoqda…' : 'Yuborilmoqda…';

  let result;
  try {
    result = await api('/api/answer', {
      session_id: state.sessionId,
      question_id: state.question.id,
      answer,
    });
  } catch (e) {
    state.busy = false;
    btn.classList.remove('is-busy');
    setSubmit(true, isFree ? 'Javobni yuborish' : 'Davom etish');
    fail(e.message);
    return;
  }

  state.busy = false;
  btn.classList.remove('is-busy');
  haptic('light');

  if (result.done) {
    showResult(result);
    return;
  }

  if (result.level_change) {
    await showLevelChange(result.level_change);
  }
  renderQuestion(result.question, result.progress);
}

/* ── Daraja o'zgarishi ─────────────────────────────────────────── */

function showLevelChange(change) {
  const up = change.direction === 'up';

  $('lu-icon').textContent = up ? '↑' : '↓';
  $('lu-arrow').textContent = up ? '↑' : '↓';
  $('lu-from').textContent = change.from_name;
  $('lu-to').textContent = change.to_name;
  $('lu-text').textContent = up
    ? `Ajoyib! Endi ${change.to_name} darajasidagi savollar beriladi.`
    : `${change.to_name} darajasidan bir nechta savol bilan tekshirib ko'ramiz.`;

  haptic(up ? 'ok' : 'up');

  const overlay = $('levelup');
  overlay.classList.add('is-shown');

  return new Promise((resolve) => {
    setTimeout(() => {
      overlay.classList.remove('is-shown');
      resolve();
    }, 2000);
  });
}

/* ── Natija ────────────────────────────────────────────────────── */

function showResult(result) {
  state.lastResult = result;
  state.sessionId = null;

  $('result-badge').textContent = result.level_name;
  $('summary').textContent = result.summary;

  renderLadder($('result-ladder'), result.level);

  const box = $('blocks');
  box.innerHTML = '';
  result.blocks.forEach((b) => {
    const row = document.createElement('div');
    row.className = 'block-row';
    row.innerHTML =
      `<span class="block-level">${b.level_short}</span>` +
      '<span class="bar"><span class="bar-fill"></span></span>' +
      `<span class="block-score">${b.correct}/${b.total}</span>`;
    box.append(row);
    // Kenglikni keyingi kadrda beramiz — shunda chiziq to'lish animatsiyasi ko'rinadi.
    requestAnimationFrame(() => {
      row.querySelector('.bar-fill').style.width = `${b.percent}%`;
    });
  });

  $('result-foot').textContent =
    `Jami ${result.total_questions} ta savol · natija Telegram chatingizga ham yuborildi`;

  haptic('ok');
  show('result');
}

/* ── Bosh ekran ────────────────────────────────────────────────── */

function renderHome(data) {
  state.name = data.name || '';
  state.lastResult = data.last_result;
  state.active = data.active;
  $('admin-btn').classList.toggle('hidden', !data.is_admin);

  $('home-title').textContent = state.name
    ? `Salom, ${state.name}!`
    : 'Daraja aniqlash testi';

  renderLadder($('home-ladder'), data.active?.progress?.level || 'A1', {
    markDone: Boolean(data.active),
  });

  // Yarim qolgan test bormi?
  const active = data.active;
  $('resume-btn').classList.toggle('hidden', !active);
  $('start-btn').textContent = active ? 'Boshidan boshlash' : 'Testni boshlash';
  if (active) {
    $('resume-btn').textContent =
      `Davom ettirish (${active.progress.level_name} · ${active.progress.asked + 1}-savol)`;
  }

  // Oldingi natija bormi?
  const card = $('last-result-card');
  card.classList.toggle('hidden', !data.last_result);
  if (data.last_result) {
    const r = data.last_result;
    $('lr-level').textContent =
      LADDER.find((l) => l.code === r.level)?.short || r.level_name;
    const when = r.finished_at ? new Date(r.finished_at) : null;
    $('lr-meta').textContent =
      `${r.level_name}${when ? ' · ' + when.toLocaleDateString('uz-UZ') : ''}`;
    card.onclick = () => { haptic('light'); showResult(r); };
  }

  show('home');
}

/* ── Admin paneli ──────────────────────────────────────────────── */

async function openAdmin() {
  let data;
  try {
    data = await api('/api/admin/results');
  } catch (e) {
    return fail(e.message);
  }

  $('admin-totals').textContent =
    `Jami ${data.totals.total} ta urinish · ${data.totals.finished} tasi tugallangan`;

  // Darajalar bo'yicha taqsimot — eng ko'pi to'liq chiziq bo'ladi.
  const levels = Object.entries(data.by_level);
  const max = Math.max(1, ...levels.map(([, n]) => n));
  const box = $('admin-levels');
  box.innerHTML = '';
  levels.forEach(([name, n]) => {
    const row = document.createElement('div');
    row.className = 'block-row';
    row.innerHTML =
      `<span class="admin-level">${name}</span>` +
      '<span class="bar"><span class="bar-fill"></span></span>' +
      `<span class="block-score">${n}</span>`;
    box.append(row);
    requestAnimationFrame(() => {
      row.querySelector('.bar-fill').style.width = `${(n / max) * 100}%`;
    });
  });

  const list = $('admin-list');
  list.innerHTML = '';
  if (!data.results.length) {
    list.innerHTML = '<p class="hint">Hali hech kim test topshirmagan.</p>';
  }
  data.results.forEach((r) => {
    const when = r.finished_at ? new Date(r.finished_at) : null;
    const row = document.createElement('div');
    row.className = 'admin-row';
    row.innerHTML =
      `<div class="admin-who"><b>${escapeHtml(r.name)}</b>` +
      (r.username ? ` <span class="hint small">@${escapeHtml(r.username)}</span>` : '') +
      `<br><span class="hint small">${when ? when.toLocaleString('uz-UZ') : ''}</span></div>` +
      `<span class="admin-badge">${escapeHtml(r.level_name)}</span>`;
    list.append(row);
  });

  show('admin');
}

/** Ismlar foydalanuvchidan keladi — HTML sifatida talqin qilinmasin. */
function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

async function openHome() {
  try {
    renderHome(await api('/api/bootstrap'));
  } catch (e) {
    fail(e.message);
  }
}

async function startTest() {
  if (state.busy) return;

  // Faqat tugallanmagan test bor bo'lsa so'raymiz — u bekor qilinadi.
  if (state.active) {
    const ok = await confirmExit(
      'Yarim qolgan testingiz bor. Uni bekor qilib, boshidan boshlaymizmi?'
    );
    if (!ok) return;
  }

  state.busy = true;
  $('start-btn').classList.add('is-busy');
  try {
    const data = await api('/api/start');
    state.sessionId = data.session_id;
    state.name = data.name;
    state.active = null;
    renderQuestion(data.question, data.progress);
    show('quiz');
  } catch (e) {
    fail(e.message);
  } finally {
    state.busy = false;
    $('start-btn').classList.remove('is-busy');
  }
}

function resumeTest() {
  const active = state.active;
  if (!active) return openHome();
  state.sessionId = active.session_id;
  renderQuestion(active.question, active.progress);
  show('quiz');
}

/* ── Ishga tushirish ───────────────────────────────────────────── */

function bindEvents() {
  $('start-btn').addEventListener('click', startTest);
  $('resume-btn').addEventListener('click', resumeTest);
  $('submit-btn').addEventListener('click', submitAnswer);
  $('error-retry').addEventListener('click', openHome);
  $('admin-btn').addEventListener('click', openAdmin);
  $('admin-back').addEventListener('click', openHome);
  $('retake-btn').addEventListener('click', startTest);
  $('close-btn').addEventListener('click', () => {
    if (tg?.close) tg.close();
    else openHome();
  });
}

async function boot() {
  initTelegram();
  bindEvents();

  try {
    const data = await api('/api/bootstrap');
    // Test yarmida qolgan bo'lsa — to'g'ridan-to'g'ri o'sha savolga qaytaramiz.
    if (data.active) {
      state.name = data.name;
      state.lastResult = data.last_result;
      state.active = data.active;
      state.sessionId = data.active.session_id;
      renderQuestion(data.active.question, data.active.progress);
      show('quiz');
      return;
    }
    renderHome(data);
  } catch (e) {
    fail(e.message);
  }
}

boot();
