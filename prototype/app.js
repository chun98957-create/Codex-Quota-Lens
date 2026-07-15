(() => {
  const root = document.getElementById('quota-lens-app');
  if (!root) return;

  const $ = selector => root.querySelector(selector);
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const fmt1 = value => Number(value || 0).toFixed(1);
  const fmtPercent = value => `${Number(value || 0).toFixed(Number(value) % 1 ? 1 : 0)}%`;
  const formatTokens = value => {
    const number = Number(value || 0);
    if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
    if (number >= 1_000) return `${Math.round(number / 1_000)}k`;
    return String(number);
  };
  const formatDuration = milliseconds => {
    const totalMinutes = Math.max(0, Math.round(milliseconds / 60000));
    const days = Math.floor(totalMinutes / 1440);
    const hours = Math.floor((totalMinutes % 1440) / 60);
    const minutes = totalMinutes % 60;
    return [days ? `${days}天` : '', hours ? `${hours}小时` : '', minutes ? `${minutes}分钟` : ''].filter(Boolean).join(' ') || '不到 1 分钟';
  };

  let snapshot = null;
  let remaining = 0;
  let resetAt = 0;
  let quotaSeries = [0, 0];
  let loading = false;

  root.querySelectorAll('[data-view]').forEach(button => {
    button.addEventListener('click', () => {
      const view = button.dataset.view;
      root.querySelectorAll('[data-view]').forEach(peer => {
        const active = peer === button;
        peer.classList.toggle('is-selected', active);
        peer.setAttribute('aria-selected', String(active));
      });
      root.querySelectorAll('.view').forEach(panel => {
        panel.hidden = panel.id !== view;
      });
    });
  });

  function renderChart() {
    const series = quotaSeries.length > 1 ? quotaSeries : [remaining, remaining];
    const width = 720;
    const height = 270;
    const left = 42;
    const right = 22;
    const top = 22;
    const bottom = 38;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const x = index => left + plotWidth * index / (series.length - 1);
    const y = value => top + (100 - clamp(value, 0, 100)) / 100 * plotHeight;
    const points = series.map((value, index) => `${x(index)},${y(value)}`).join(' ');
    const areaPoints = `${left},${top + plotHeight} ${points} ${x(series.length - 1)},${top + plotHeight}`;
    const grid = $('#chart-grid');
    grid.innerHTML = '';
    [100, 75, 50, 25, 0].forEach(value => {
      const yy = y(value);
      grid.insertAdjacentHTML('beforeend', `<line class="gridline" x1="${left}" y1="${yy}" x2="${left + plotWidth}" y2="${yy}"></line><text class="axis-text" x="${left - 8}" y="${yy + 4}" text-anchor="end">${value}%</text>`);
    });
    [['24h', 0], ['18h', .25], ['12h', .5], ['6h', .75], ['现在', 1]].forEach(([label, ratio]) => {
      const xx = left + plotWidth * ratio;
      grid.insertAdjacentHTML('beforeend', `<text class="axis-text" x="${xx}" y="${height - 10}" text-anchor="middle">${label}</text>`);
    });
    $('#area-path').setAttribute('d', `M ${areaPoints.replaceAll(' ', ' L ')} Z`);
    $('#line-path').setAttribute('d', `M ${points.replaceAll(' ', ' L ')}`);
    const budgetPerHour = Number(snapshot?.quota?.budget_pph || 0);
    const budgetEnd = clamp(series[0] - budgetPerHour * 24, 0, 100);
    $('#budget-path').setAttribute('d', `M ${left},${y(series[0])} L ${left + plotWidth},${y(budgetEnd)}`);
    const dotX = x(series.length - 1);
    const dotY = y(remaining);
    $('#current-dot').setAttribute('cx', dotX);
    $('#current-dot').setAttribute('cy', dotY);
    $('#current-label').setAttribute('x', dotX - 10);
    $('#current-label').setAttribute('y', dotY - 12);
    $('#current-label').textContent = fmtPercent(remaining);
    $('#quota-chart-desc').textContent = `本地额度历史显示剩余额度从 ${fmtPercent(series[0])} 变化到 ${fmtPercent(remaining)}。`;
  }

  function renderHeatmap(data) {
    const heatmap = $('#heatmap');
    const days = data?.days || ['一', '二', '三', '四', '五', '六', '日'];
    const hours = data?.hours || [0, 3, 6, 9, 12, 15, 18, 21];
    const values = data?.values || hours.map(() => days.map(() => 0));
    const max = Math.max(Number(data?.max || 0), 1);
    let selected = { row: 0, column: 0, value: 0 };
    values.forEach((row, rowIndex) => row.forEach((value, columnIndex) => {
      if (value > selected.value) selected = { row: rowIndex, column: columnIndex, value };
    }));
    heatmap.innerHTML = '<span></span>';
    days.forEach(day => heatmap.insertAdjacentHTML('beforeend', `<span class="heat-label">周${day}</span>`));
    hours.forEach((hour, row) => {
      heatmap.insertAdjacentHTML('beforeend', `<span class="heat-label">${String(hour).padStart(2, '0')}:00</span>`);
      values[row].forEach((rawValue, column) => {
        const value = Number(rawValue || 0);
        const isSelected = row === selected.row && column === selected.column && selected.value > 0;
        const intensity = Math.round(8 + value / max * 78);
        heatmap.insertAdjacentHTML('beforeend', `<button type="button" class="heat-cell" style="--heat:${intensity}%" aria-label="周${days[column]} ${String(hour).padStart(2, '0')}:00，${fmt1(value)}% 每小时" aria-pressed="${isSelected}">${value ? fmt1(value) : '0'}</button>`);
      });
    });
    heatmap.querySelectorAll('.heat-cell').forEach(cell => {
      cell.addEventListener('click', () => {
        heatmap.querySelectorAll('.heat-cell').forEach(peer => peer.setAttribute('aria-pressed', String(peer === cell)));
        const label = cell.getAttribute('aria-label').replace('，', ' · ');
        $('#heat-detail').innerHTML = `<span>已选择：${label}</span><span class="muted">本地额度快照计算值</span>`;
      });
    });
    if (selected.value > 0) {
      const selectedHour = String(hours[selected.row]).padStart(2, '0');
      $('#heat-detail').innerHTML = `<span>最快聚合时段：周${days[selected.column]} ${selectedHour}:00 · ${fmt1(selected.value)}%/h</span><span class="muted">本地额度快照计算值</span>`;
    } else {
      $('#heat-detail').innerHTML = '<span>历史样本暂不足以计算热力图</span><span class="muted">继续使用 Codex 后会自动积累</span>';
    }
  }

  function renderFastest(items) {
    const list = $('#speed-list');
    list.innerHTML = '';
    if (!items?.length) {
      list.innerHTML = '<div class="card muted small">暂时没有跨度超过 5 分钟的有效消耗区间。</div>';
      return;
    }
    const max = Math.max(...items.map(item => Number(item.burn_pph || 0)), 1);
    items.forEach(item => {
      const value = Number(item.burn_pph || 0);
      list.insertAdjacentHTML('beforeend', `<div class="speed-row"><div><div>${item.label}</div><div class="muted small">额度下降 ${fmt1(item.delta_percent)}%</div></div><div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${value / max * 100}%"></div></div><strong>${fmt1(value)}%/h</strong></div>`);
    });
  }

  function updatePlanner() {
    const modelFactor = Number($('#model').value);
    const effortFactor = Number($('#effort').value);
    const taskCount = Number($('#tasks').value);
    const sizeValue = Number($('#size').value);
    const sizeLabels = ['很小', '较小', '常规', '较大', '大型'];
    $('#task-value').textContent = `${taskCount} 个`;
    $('#size-value').textContent = sizeLabels[sizeValue - 1];
    if (!snapshot?.quota) return;

    const quota = snapshot.quota;
    const daysLeft = Math.max(Number(quota.hours_until_reset || 0) / 24, 1 / 24);
    const observedBurn = Number(quota.burn_pph || 0);
    const basePerTask = observedBurn > 0 ? clamp(observedBurn / 4, .15, 3) : .55;
    const sizeFactor = .45 + sizeValue * .18;
    const daily = taskCount * basePerTask * modelFactor * effortFactor * sizeFactor;
    const total = daily * daysLeft;
    const end = clamp(Math.round(remaining - total), 0, 100);
    const denominator = daysLeft * basePerTask * modelFactor * effortFactor * sizeFactor;
    const safe = clamp(Math.floor((remaining - 10) / Math.max(denominator, .01)), 1, 99);
    const risk = clamp(Math.round(total / Math.max(remaining, 1) * 52 - 6), 3, 96);
    const sustainable = end >= 10;
    $('#daily-cost').textContent = `${fmt1(daily)}%`;
    $('#daily-range').textContent = `区间 ${fmt1(daily * .7)}–${fmt1(daily * 1.4)}%`;
    $('#end-remaining').textContent = `${end}%`;
    $('#risk-label').textContent = `提前耗尽风险 ${risk}%`;
    $('#safe-tasks').textContent = `${safe} 个/天`;
    $('#meter-fill').style.width = `${clamp(total / Math.max(remaining, 1) * 100, 0, 100)}%`;
    $('#plan-status').textContent = sustainable ? '可持续' : '可能提前耗尽';
    $('#plan-copy').textContent = sustainable
      ? `按当前真实余额，这个组合预计可坚持到重置，并保留约 ${end}% 额度。`
      : `预计需要 ${Math.round(total)}% 额度；建议降至每天 ${safe} 个任务或切换更轻量模型。`;
    $('#planner-basis').textContent = observedBurn > 0
      ? `真实剩余 ${fmtPercent(remaining)} · 过去 ${quota.burn_window_minutes || 0} 分钟速度基线`
      : `真实剩余 ${fmtPercent(remaining)} · 当前速度样本不足`;
  }

  function updateCountdown() {
    if (!resetAt) {
      $('#reset-countdown').textContent = '--:--:--';
      return;
    }
    const seconds = Math.max(0, Math.floor((resetAt - Date.now()) / 1000));
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    $('#reset-countdown').textContent = `${days ? `${days}天 ` : ''}${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  }

  function updateLiveData(data) {
    snapshot = data;
    const quota = data.quota;
    remaining = Number(quota.remaining_percent || 0);
    resetAt = quota.resets_at ? Date.parse(quota.resets_at) : 0;
    quotaSeries = (data.history || []).map(point => Number(point.remaining_percent));
    if (!quotaSeries.length) quotaSeries = [remaining, remaining];
    if (quotaSeries.length === 1) quotaSeries.unshift(quotaSeries[0]);

    $('#remaining').textContent = fmtPercent(remaining);
    $('#used-label').textContent = `本窗口已使用 ${fmtPercent(quota.used_percent)}`;
    $('#burn-title').textContent = quota.burn_window_minutes ? `过去 ${quota.burn_window_minutes} 分钟` : '最近速度';
    $('#burn').textContent = `${fmt1(quota.burn_pph)}%/h`;
    $('#budget-label').textContent = `预算速度 ${fmt1(quota.budget_pph)}%/h`;
    $('#chart-caption').textContent = `${data.history?.length || 0} 个真实快照 · 最近 24 小时或当前额度窗口`;

    const burn = Number(quota.burn_pph || 0);
    const budget = Number(quota.budget_pph || 0);
    if (!burn) {
      $('#forecast').textContent = '最近未检测到额度下降';
      $('#insight').textContent = '当前真实额度稳定；继续使用后将自动计算消耗速度和耗尽时间。';
    } else {
      const forecastAt = quota.forecast_exhausts_at ? Date.parse(quota.forecast_exhausts_at) : 0;
      if (forecastAt && resetAt && forecastAt < resetAt) {
        $('#forecast').textContent = `可能提前 ${formatDuration(resetAt - forecastAt)} 用完`;
      } else {
        const forecastRemaining = clamp(remaining - burn * Number(quota.hours_until_reset || 0), 0, 100);
        $('#forecast').textContent = `按当前速度重置时约剩 ${fmtPercent(forecastRemaining)}`;
      }
      const ratio = budget > 0 ? burn / budget : 0;
      const pressure = ratio >= 5
        ? `约为预算速度的 ${Math.round(ratio)} 倍`
        : `比预算速度快 ${Math.round((ratio - 1) * 100)}%`;
      $('#insight').textContent = ratio > 1.2
        ? `当前真实消耗速度${pressure}。优先把常规任务切换到更轻量模型或降低推理强度。`
        : `当前真实消耗节奏在预算范围内，可以按现有计划继续使用。`;
    }

    const latestTokens = data.tokens?.latest;
    $('#token-mix').textContent = latestTokens
      ? `最近调用：输入 ${formatTokens(latestTokens.input_tokens)} · 缓存 ${formatTokens(latestTokens.cached_input_tokens)} · 输出 ${formatTokens(latestTokens.output_tokens)} · 推理 ${formatTokens(latestTokens.reasoning_output_tokens)} tokens`
      : '尚未找到最近一次 token 明细';
    $('#quality-label').textContent = `可信度 B · ${data.source.rate_limit_events} 条额度事件`;
    $('#source-status').classList.remove('is-error');
    $('#source-status').innerHTML = `<span class="status-dot"></span>真实数据 · ${data.source.files_scanned} 个会话文件 · 5 秒刷新`;

    renderChart();
    renderHeatmap(data.heatmap);
    renderFastest(data.fastest);
    updatePlanner();
    updateCountdown();
  }

  async function loadLiveData(manual = false) {
    if (loading) return;
    loading = true;
    const refresh = $('#refresh');
    refresh.disabled = true;
    refresh.textContent = manual ? '刷新中…' : '正在同步';
    try {
      const response = await fetch(`/api/snapshot?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data.mode !== 'live') throw new Error(data.error || '没有可用额度事件');
      updateLiveData(data);
    } catch (error) {
      $('#source-status').classList.add('is-error');
      $('#source-status').innerHTML = '<span class="status-dot"></span>真实数据连接失败';
      $('#insight').textContent = `无法读取本地额度：${error.message}。请使用 prototype/server.py 启动页面。`;
    } finally {
      loading = false;
      refresh.disabled = false;
      refresh.textContent = '立即刷新';
    }
  }

  $('#refresh').addEventListener('click', () => loadLiveData(true));
  ['#model', '#effort', '#tasks', '#size'].forEach(selector => $(selector).addEventListener('input', updatePlanner));
  setInterval(updateCountdown, 1000);
  setInterval(() => loadLiveData(false), 5000);
  loadLiveData(false);
})();
