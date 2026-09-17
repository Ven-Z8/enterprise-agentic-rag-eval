/**
 * RAGFilings — Force-Directed Fact & Knowledge Graph Engine
 * High-performance, anti-flicker physics simulation with alpha cooling,
 * Retina high-DPI scaling, smooth damping, and interactive inspection.
 */

(function () {
  let canvas = null;
  let ctx = null;
  let nodes = [];
  let edges = [];
  let draggedNode = null;
  let hoveredNode = null;
  let animationRunning = false;
  let currentFilter = 'ALL';
  let alpha = 1.0;
  let dpr = 1;
  let logicalWidth = 320;
  let logicalHeight = 220;

  // Tooltip element
  let tooltipEl = null;

  function ensureTooltip() {
    if (!tooltipEl && canvas && canvas.parentElement) {
      tooltipEl = document.createElement('div');
      tooltipEl.className = 'graph-node-tooltip';
      tooltipEl.style.position = 'absolute';
      tooltipEl.style.pointerEvents = 'none';
      tooltipEl.style.display = 'none';
      tooltipEl.style.zIndex = '50';
      canvas.parentElement.appendChild(tooltipEl);
    }
  }

  function init(canvasElement, graphData) {
    if (!canvasElement) return;
    canvas = canvasElement;
    ctx = canvas.getContext('2d');
    dpr = window.devicePixelRatio || 1;

    const rect = canvas.parentElement ? canvas.parentElement.getBoundingClientRect() : canvas.getBoundingClientRect();
    logicalWidth = Math.max(280, rect.width || 320);
    logicalHeight = Math.max(180, rect.height || 220);

    canvas.width = Math.round(logicalWidth * dpr);
    canvas.height = Math.round(logicalHeight * dpr);
    canvas.style.width = `${logicalWidth}px`;
    canvas.style.height = `${logicalHeight}px`;

    ensureTooltip();

    if (!graphData || !graphData.nodes || graphData.nodes.length === 0) {
      nodes = [];
      edges = [];
      render();
      return;
    }

    const rawNodes = graphData.nodes;
    const centerX = logicalWidth / 2;
    const centerY = logicalHeight / 2;
    const angleStep = (Math.PI * 2) / Math.max(1, rawNodes.length);

    // Initial positioning in an organic circular layout to prevent explosive repulsion
    nodes = rawNodes.map((n, i) => {
      const angle = i * angleStep;
      const radiusDist = n.type === 'entity' ? 30 : 65 + (i % 3) * 15;
      const initialX = centerX + Math.cos(angle) * radiusDist;
      const initialY = centerY + Math.sin(angle) * radiusDist;

      return {
        ...n,
        x: n.x !== undefined ? n.x : initialX,
        y: n.y !== undefined ? n.y : initialY,
        vx: 0,
        vy: 0,
        radius: n.type === 'entity' ? 14 : 10
      };
    });

    edges = (graphData.links || [])
      .map(l => {
        const fromId = Array.isArray(l) ? l[0] : (l.source?.id || l.source);
        const toId = Array.isArray(l) ? l[1] : (l.target?.id || l.target);
        return {
          source: nodes.find(n => n.id === fromId),
          target: nodes.find(n => n.id === toId),
          relation: l.relation || 'RELATES_TO'
        };
      })
      .filter(e => e.source && e.target);

    attachEvents();

    // Start cooled simulation
    alpha = 0.85;
    if (!animationRunning) {
      animationRunning = true;
      requestAnimationFrame(step);
    }
  }

  function setFilter(filter) {
    currentFilter = filter;
    // Wake up physics slightly to gracefully rearrange
    alpha = Math.max(alpha, 0.3);
    if (!animationRunning) {
      animationRunning = true;
      requestAnimationFrame(step);
    }
  }

  function step() {
    if (!canvas || !ctx) return;

    // Simulation parameters
    const damping = 0.74;
    const springK = 0.035;
    const restLength = 65;
    const repulsionStrength = 1400;
    const centerPull = 0.045;
    const cx = logicalWidth / 2;
    const cy = logicalHeight / 2;

    // Center gravity pull
    nodes.forEach(node => {
      if (node !== draggedNode) {
        node.vx += (cx - node.x) * centerPull * alpha;
        node.vy += (cy - node.y) * centerPull * alpha;
      }
    });

    // Spring tension along connected edges
    edges.forEach(edge => {
      const dx = edge.target.x - edge.source.x;
      const dy = edge.target.y - edge.source.y;
      const dist = Math.hypot(dx, dy) || 1;
      const displacement = (dist - restLength) * springK * alpha;
      const fx = (dx / dist) * displacement;
      const fy = (dy / dist) * displacement;

      if (edge.source !== draggedNode) {
        edge.source.vx += fx;
        edge.source.vy += fy;
      }
      if (edge.target !== draggedNode) {
        edge.target.vx -= fx;
        edge.target.vy -= fy;
      }
    });

    // Inverse-square repulsion (Coulomb) with soft denominator to eliminate jitter
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const n1 = nodes[i];
        const n2 = nodes[j];
        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;
        const distSq = dx * dx + dy * dy + 180;
        const dist = Math.sqrt(distSq);

        if (dist < 150) {
          const force = (repulsionStrength / distSq) * alpha;
          const rx = (dx / dist) * force;
          const ry = (dy / dist) * force;

          if (n1 !== draggedNode) {
            n1.vx -= rx;
            n1.vy -= ry;
          }
          if (n2 !== draggedNode) {
            n2.vx += rx;
            n2.vy += ry;
          }
        }
      }
    }

    // Velocity integration & bounds clamping
    let totalKineticEnergy = 0;
    const maxVelocity = 3.0 * alpha;

    nodes.forEach(node => {
      if (node !== draggedNode) {
        // Clamp maximum speed per step
        const speed = Math.hypot(node.vx, node.vy);
        if (speed > maxVelocity && speed > 0) {
          node.vx = (node.vx / speed) * maxVelocity;
          node.vy = (node.vy / speed) * maxVelocity;
        }

        node.vx *= damping;
        node.vy *= damping;
        node.x += node.vx;
        node.y += node.vy;

        // Soft padding boundary
        const pad = node.radius + 14;
        node.x = Math.max(pad, Math.min(logicalWidth - pad, node.x));
        node.y = Math.max(pad, Math.min(logicalHeight - pad, node.y));

        totalKineticEnergy += node.vx * node.vx + node.vy * node.vy;
      }
    });

    render();

    // Alpha cooling decay
    alpha *= 0.965;

    // Convergence check: STOP simulation completely when energy settles!
    if (alpha < 0.005 || (totalKineticEnergy < 0.015 && alpha < 0.2)) {
      animationRunning = false;
      // Final static render
      render();
      return;
    }

    requestAnimationFrame(step);
  }

  function render() {
    if (!ctx) return;

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, logicalWidth, logicalHeight);

    // Subtle background coordinate grid dots
    ctx.fillStyle = 'rgba(57, 57, 59, 0.4)';
    const gridSpacing = 24;
    for (let x = 12; x < logicalWidth; x += gridSpacing) {
      for (let y = 12; y < logicalHeight; y += gridSpacing) {
        ctx.fillRect(x, y, 1, 1);
      }
    }

    // Render Edges
    edges.forEach(edge => {
      const isConnectedToHovered = hoveredNode && (edge.source === hoveredNode || edge.target === hoveredNode);
      ctx.beginPath();
      ctx.moveTo(edge.source.x, edge.source.y);
      ctx.lineTo(edge.target.x, edge.target.y);

      if (isConnectedToHovered) {
        ctx.strokeStyle = '#049fd9';
        ctx.lineWidth = 1.8;
      } else {
        ctx.strokeStyle = '#262628';
        ctx.lineWidth = 1.1;
      }
      ctx.stroke();
    });

    // Render Nodes
    nodes.forEach(node => {
      const isFiltered = currentFilter !== 'ALL' &&
        node.ticker !== currentFilter &&
        node.id !== currentFilter &&
        node.id !== `company:${currentFilter}`;

      const isHovered = hoveredNode === node;
      const alphaVal = isFiltered ? 0.25 : 1.0;

      ctx.save();
      ctx.globalAlpha = alphaVal;

      // Color coding & aura
      let fillColor = '#049fd9';
      let strokeColor = '#38bdf8';

      if (node.type === 'entity') {
        fillColor = '#049fd9';
        strokeColor = '#ffffff';
        // Subtle glow around main entity
        ctx.shadowColor = 'rgba(4, 159, 217, 0.6)';
        ctx.shadowBlur = isHovered ? 14 : 8;
      } else if (node.type === 'metric') {
        fillColor = '#059669';
        strokeColor = '#34d399';
      } else if (node.type === 'period') {
        fillColor = '#d97706';
        strokeColor = '#fbbf24';
      } else if (node.type === 'section') {
        fillColor = '#7c3aed';
        strokeColor = '#c084fc';
      }

      // Outer highlight ring on hover
      if (isHovered) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 4, 0, Math.PI * 2);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fillStyle = fillColor;
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1.8;
      ctx.fill();
      ctx.stroke();

      // Reset shadow for labels
      ctx.shadowBlur = 0;

      // Formatted Label with dark pill backing
      const rawLabel = node.label || node.id || '';
      const displayLabel = rawLabel.length > 14 ? rawLabel.slice(0, 12) + '…' : rawLabel;

      ctx.font = '500 9px Inter, -apple-system, sans-serif';
      const textMetrics = ctx.measureText(displayLabel);
      const textWidth = textMetrics.width;
      const pillHeight = 13;
      const pillWidth = textWidth + 8;
      const pillX = node.x - pillWidth / 2;
      const pillY = node.y + node.radius + 4;

      // Pill background
      ctx.fillStyle = 'rgba(15, 23, 32, 0.85)';
      ctx.strokeStyle = '#39393b';
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.roundRect(pillX, pillY, pillWidth, pillHeight, 3);
      ctx.fill();
      ctx.stroke();

      // Pill text
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(displayLabel, node.x, pillY + pillHeight / 2);

      ctx.restore();
    });

    ctx.restore();
  }

  let eventsAttached = false;
  function attachEvents() {
    if (eventsAttached || !canvas) return;
    eventsAttached = true;

    function getMousePos(e) {
      const rect = canvas.getBoundingClientRect();
      return {
        x: e.clientX - rect.x,
        y: e.clientY - rect.y
      };
    }

    function findNodeAt(mx, my) {
      for (let i = nodes.length - 1; i >= 0; i--) {
        const n = nodes[i];
        if (Math.hypot(n.x - mx, n.y - my) <= n.radius + 8) {
          return n;
        }
      }
      return null;
    }

    canvas.addEventListener('mousedown', e => {
      const pos = getMousePos(e);
      draggedNode = findNodeAt(pos.x, pos.y);
      if (draggedNode) {
        canvas.style.cursor = 'grabbing';
        alpha = Math.max(alpha, 0.4);
        if (!animationRunning) {
          animationRunning = true;
          requestAnimationFrame(step);
        }
      }
    });

    window.addEventListener('mousemove', e => {
      if (!canvas) return;
      const pos = getMousePos(e);

      if (draggedNode) {
        const pad = draggedNode.radius + 6;
        draggedNode.x = Math.max(pad, Math.min(logicalWidth - pad, pos.x));
        draggedNode.y = Math.max(pad, Math.min(logicalHeight - pad, pos.y));
        draggedNode.vx = 0;
        draggedNode.vy = 0;
        alpha = Math.max(alpha, 0.2);
        if (!animationRunning) {
          animationRunning = true;
          requestAnimationFrame(step);
        }
      } else {
        const nodeUnder = findNodeAt(pos.x, pos.y);
        if (nodeUnder !== hoveredNode) {
          hoveredNode = nodeUnder;
          canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
          updateTooltip(hoveredNode, pos.x, pos.y);
          if (!animationRunning) {
            render();
          }
        } else if (hoveredNode) {
          updateTooltip(hoveredNode, pos.x, pos.y);
        }
      }
    });

    window.addEventListener('mouseup', () => {
      if (draggedNode) {
        draggedNode = null;
        if (canvas) canvas.style.cursor = hoveredNode ? 'pointer' : 'grab';
      }
    });

    canvas.addEventListener('mouseleave', () => {
      hoveredNode = null;
      if (tooltipEl) tooltipEl.style.display = 'none';
      if (!animationRunning) render();
    });
  }

  function updateTooltip(node, x, y) {
    if (!tooltipEl) return;
    if (!node) {
      tooltipEl.style.display = 'none';
      return;
    }

    const typeUpper = (node.type || 'ENTITY').toUpperCase();
    let valStr = '';
    if (node.value !== undefined && node.value !== null) {
      valStr = `<div style="color:#34d399; margin-top:2px;">Value: $${Number(node.value).toLocaleString()}M</div>`;
    }

    tooltipEl.innerHTML = `
      <div style="font-weight:700; color:#ffffff; margin-bottom:2px;">${node.label || node.id}</div>
      <div style="font-size:9px; color:#049fd9;">TYPE: ${typeUpper}</div>
      ${node.fiscal_year ? `<div style="color:#fbbf24;">Fiscal Year: ${node.fiscal_year}</div>` : ''}
      ${valStr}
    `;

    tooltipEl.style.display = 'block';
    tooltipEl.style.left = `${Math.min(logicalWidth - 140, Math.max(10, x + 12))}px`;
    tooltipEl.style.top = `${Math.min(logicalHeight - 60, Math.max(10, y - 20))}px`;
  }

  window.GraphEngine = {
    init,
    setFilter
  };
})();
