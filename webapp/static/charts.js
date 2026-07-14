/* 외부 라이브러리 없이 캔버스 2D API만으로 그리는 최소 산포도.
   drawScatterChart(canvasId, series, opts)
     series: [{ label, color, points: [{x, y, name}] }]
     opts:   { xLabel, yLabel, vLine, hLine }  (vLine/hLine은 기준선 x/y 값, 선택) */
function drawScatterChart(canvasId, series, opts) {
  opts = opts || {};
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const pad = { l: 46, r: 16, t: 16, b: 40 };

  const allPoints = series.flatMap(s => s.points);
  if (!allPoints.length) {
    ctx.fillStyle = "#888";
    ctx.font = "13px sans-serif";
    ctx.fillText("표시할 데이터가 없습니다.", pad.l, H / 2);
    return;
  }

  let xs = allPoints.map(p => p.x), ys = allPoints.map(p => p.y);
  if (opts.vLine !== undefined) xs.push(opts.vLine);
  if (opts.hLine !== undefined) ys.push(opts.hLine);
  let xMin = Math.min(...xs), xMax = Math.max(...xs);
  let yMin = Math.min(...ys), yMax = Math.max(...ys);
  const xPad = (xMax - xMin) * 0.08 || 1, yPad = (yMax - yMin) * 0.08 || 1;
  xMin -= xPad; xMax += xPad; yMin -= yPad; yMax += yPad;

  const sx = x => pad.l + ((x - xMin) / (xMax - xMin)) * (W - pad.l - pad.r);
  const sy = y => H - pad.b - ((y - yMin) / (yMax - yMin)) * (H - pad.t - pad.b);

  ctx.clearRect(0, 0, W, H);

  // 축
  ctx.strokeStyle = "#999";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, H - pad.b); ctx.lineTo(W - pad.r, H - pad.b);
  ctx.stroke();

  // 기준선(강한 이상 임계값)
  ctx.strokeStyle = "#c0392b55";
  ctx.setLineDash([4, 4]);
  if (opts.vLine !== undefined) {
    ctx.beginPath(); ctx.moveTo(sx(opts.vLine), pad.t); ctx.lineTo(sx(opts.vLine), H - pad.b); ctx.stroke();
  }
  if (opts.hLine !== undefined) {
    ctx.beginPath(); ctx.moveTo(pad.l, sy(opts.hLine)); ctx.lineTo(W - pad.r, sy(opts.hLine)); ctx.stroke();
  }
  ctx.setLineDash([]);

  // 점
  for (const s of series) {
    ctx.fillStyle = s.color;
    for (const p of s.points) {
      ctx.beginPath();
      ctx.arc(sx(p.x), sy(p.y), 4.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // 축 라벨
  ctx.fillStyle = "#888";
  ctx.font = "11px sans-serif";
  if (opts.xLabel) ctx.fillText(opts.xLabel, W - pad.r - ctx.measureText(opts.xLabel).width, H - 8);
  if (opts.yLabel) {
    ctx.save();
    ctx.translate(12, pad.t + 8);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(opts.yLabel, 0, 0);
    ctx.restore();
  }
}
