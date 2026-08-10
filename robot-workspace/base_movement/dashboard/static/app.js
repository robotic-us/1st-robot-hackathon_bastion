const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let solarResult = null;
let toastTimer = null;
let lastJobStatus = null;

function localDateTimeValue(date = new Date()) {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 16);
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}

function setBusy(busy) {
  $$('button').forEach(button => {
    if (!button.closest('#warningModal')) button.disabled = busy;
  });
}

function heightSelection(value) {
  if (value >= 190) return {slot: 45, label: '5단계 · 250°'};
  if (value >= 180) return {slot: 44, label: '4단계 · 200°'};
  if (value >= 170) return {slot: 43, label: '3단계 · 150°'};
  if (value >= 160) return {slot: 42, label: '2단계 · 100°'};
  if (value >= 150) return {slot: 41, label: '1단계 · 50°'};
  return {slot: null, label: '기본 높이 · 0°'};
}

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `요청 실패 (${response.status})`);
  return body;
}

async function submitAction(request) {
  try {
    const result = await api('/api/action', {method: 'POST', body: JSON.stringify(request)});
    if (result.warning && !result.accepted) {
      showWarning(result.warnings);
      return;
    }
    toast('동작을 시작했습니다');
    await refreshState();
  } catch (error) { toast(error.message); }
}

function showWarning(warnings) {
  $('#warningDetails').innerHTML = warnings.map(w => {
    const axes = (w.mismatches || []).map(m =>
      `<div>${m.axis} · 새 모션 시작 ${m.expected}° / 이전 모션 종료 ${m.actual}° <b>(${m.difference > 0 ? '+' : ''}${m.difference}°)</b></div>`).join('');
    return `<div class="warning-row"><strong>모션 ${w.slot}</strong> · ${w.reason}${axes}</div>`;
  }).join('');
  $('#warningModal').classList.add('open');
  $('#warningModal').setAttribute('aria-hidden', 'false');
}

function hideWarning() {
  $('#warningModal').classList.remove('open');
  $('#warningModal').setAttribute('aria-hidden', 'true');
}

async function calculateSolar() {
  try {
    solarResult = await api('/api/solar', {method: 'POST', body: JSON.stringify({
      latitude: Number($('#latitude').value), longitude: Number($('#longitude').value),
      datetime: $('#dateTime').value
    })});
    $('#sunElevation').textContent = `${solarResult.elevation_deg.toFixed(1)}°`;
    $('#selectedTilt').textContent = `${solarResult.selected_tilt_deg > 0 ? '+' : ''}${solarResult.selected_tilt_deg}°`;
    $('#umbrellaArm').style.transform = `rotate(${solarResult.selected_tilt_deg}deg)`;
  } catch (error) { toast(error.message); }
}

function renderHistory(history) {
  const log = $('#activityLog');
  if (!history?.length) { log.innerHTML = '<p class="empty">아직 실행 기록이 없습니다.</p>'; return; }
  log.innerHTML = history.map(item => `<div class="activity-item ${item.kind || ''}"><i></i><div><strong>${item.message}</strong><time>${new Date(item.at).toLocaleString('ko-KR')}</time></div></div>`).join('');
}

async function refreshState() {
  try {
    const data = await api('/api/state');
    const {state, job} = data;
    const busy = job?.status === 'running';
    setBusy(busy);
    $('#statusDot').className = `status-dot ${busy ? 'busy' : 'online'}`;
    $('#robotStatus').textContent = busy ? '동작 실행 중' : '명령 대기';
    $('#heightMetric').textContent = state.height_slot ? `${state.height_slot - 40}단계` : '기본';
    $('#heightSub').textContent = state.height_slot ? `${(state.height_slot - 40) * 50}°` : '0°';
    $('#tiltMetric').textContent = `${state.tilt_deg > 0 ? '+' : ''}${state.tilt_deg || 0}°`;
    $('#tiltSub').textContent = state.tilt_slot ? `모션 ${state.tilt_slot}` : '기본 각도';
    $('#motionMetric').textContent = busy ? `${job.step}/${job.total}` : job?.status === 'failed' ? '오류' : '대기';
    $('#motionSub').textContent = busy ? job.current : job?.error || '명령을 선택하세요';
    $('#modeTag').textContent = data.dry_run ? 'DEMO · DRY RUN' : 'ROBOT LIVE';
    renderHistory(state.history);
    if (lastJobStatus === 'running' && job?.status === 'completed') toast('모든 동작이 완료되었습니다');
    if (lastJobStatus === 'running' && job?.status === 'failed') toast(`동작 실패: ${job.error}`);
    lastJobStatus = job?.status;
  } catch (_) {
    $('#robotStatus').textContent = '서버 연결 끊김';
    $('#statusDot').className = 'status-dot';
  }
}

$('#dateTime').value = localDateTimeValue();
$('#heightInput').addEventListener('input', e => {
  $('#heightRecommendation').textContent = heightSelection(Number(e.target.value)).label;
});
$('#heightAction').addEventListener('click', () => submitAction({kind: 'height', height_cm: Number($('#heightInput').value), label: `키 ${$('#heightInput').value}cm 높이 적용`}));
$$('.parking-spot').forEach(button => button.addEventListener('click', () => submitAction({kind: 'parking', spot: Number(button.dataset.spot), label: `${button.dataset.spot}번 주차 위치 왕복`})));
$$('.motion-button').forEach(button => button.addEventListener('click', () => submitAction({kind: 'manual', slot: Number(button.dataset.slot), label: `수동 모션 ${button.dataset.slot} · ${button.querySelector('strong').textContent}`})));
$('#solarCalculate').addEventListener('click', calculateSolar);
$('#solarAction').addEventListener('click', async () => {
  if (!solarResult) await calculateSolar();
  if (solarResult) submitAction({kind: 'tilt', motion_id: solarResult.motion_id, label: `태양 추적 ${solarResult.selected_tilt_deg}°`});
});
$('#cancelWarning').addEventListener('click', () => { hideWarning(); toast('실행이 차단되었습니다'); });
$('#forceAction').style.display = 'none';
setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('ko-KR', {hour: '2-digit', minute: '2-digit', hour12: false}); }, 1000);
setInterval(refreshState, 900);
$('#heightRecommendation').textContent = heightSelection(Number($('#heightInput').value)).label;
calculateSolar();
refreshState();
