document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('start-game-form');
    const startButton = document.getElementById('start-battle-btn');
    const winnerContainer = document.getElementById('winner-container');
    const winnerText = document.getElementById('winner-text');
    const winnerReason = document.getElementById('winner-reason');
    let gameId = null;
    let isGameRunning = false;

    let whiteTime = 0;
    let blackTime = 0;
    let whiteCost = 0;
    let blackCost = 0;
    let turn = 'white';
    let moveRetryCount = 0;
    let whiteDisplayName = '';
    let blackDisplayName = '';
    let isOffline = !navigator.onLine;
    let eventSource = null;

    // Stockfish evaluation (minimal integration)
    let sfWorker = null;
    let sfReady = false;
    const EVAL_DEPTH = 12; // increase for higher precision (slower)
    const EVAL_MAX_CP = 1000; // centipawn cap for bar mapping
    let lastSideToMove = 'w';
    let lastEvaluatedFEN = '';
    let evalTimer = null;

    function initStockfish() {
        function attachListeners(workerLike) {
            if (!workerLike) return;
            workerLike.onmessage = function(e) {
                const msg = (e && e.data) ? String(e.data) : '';
                if (!msg) return;
                if (msg.indexOf('uciok') !== -1) {
                    sfReady = true;
                    try { workerLike.postMessage('setoption name Threads value 1'); } catch (err) {}
                    return;
                }
                if (msg.startsWith('info ') && msg.indexOf('score ') !== -1) {
                    const s = parseScoreFromInfo(msg);
                    if (!s) return;
                    let cp;
                    if (s.kind === 'cp') cp = s.value;
                    else if (s.kind === 'mate') cp = (s.value >= 0 ? 1 : -1) * EVAL_MAX_CP;
                    else return;
                    const whiteCp = (lastSideToMove === 'w') ? cp : -cp;
                    const p = cpToWhitePercent(whiteCp);
                    setEvalBar(p);
                }
            };
            try { workerLike.postMessage('uci'); } catch (e) {}
        }

        try {
            sfWorker = new Worker('/static/js/stockfish.js');
            sfWorker.onerror = function(err) {
                try { sfWorker.terminate(); } catch (e2) {}
                sfWorker = null;
                loadCdnInline();
            };
            attachListeners(sfWorker);
            return;
        } catch (e) {
            console.warn('Worker failed, trying inline Stockfish()', e);
        }

        function loadCdnInline() {
            try {
                if (!window.Stockfish) {
                    const s = document.createElement('script');
                    s.src = 'https://cdn.jsdelivr.net/npm/stockfish@16/stockfish.js';
                    s.onload = function() {
                        try {
                            sfWorker = window.Stockfish();
                            attachListeners(sfWorker);
                        } catch (err) {
                            console.error('Inline Stockfish() failed:', err);
                        }
                    };
                    s.onerror = function() {
                        console.error('Failed to load Stockfish from CDN');
                    };
                    document.head.appendChild(s);
                } else {
                    sfWorker = window.Stockfish();
                    attachListeners(sfWorker);
                }
            } catch (e) {
                console.error('Stockfish init failed:', e);
            }
        }

        // Fallback: load script from CDN and use window.Stockfish()
        loadCdnInline();
    }

    function parseScoreFromInfo(line) {
        try {
            const parts = line.split(' ');
            const i = parts.indexOf('score');
            if (i === -1 || i + 2 >= parts.length) return null;
            const t = parts[i + 1];
            const v = parseInt(parts[i + 2], 10);
            if (t === 'cp' && !isNaN(v)) return { kind: 'cp', value: v };
            if (t === 'mate' && !isNaN(v)) return { kind: 'mate', value: v };
            return null;
        } catch (e) { return null; }
    }

    function evaluateFEN(fen) {
        if (!sfWorker || !sfReady) return;
        lastSideToMove = (fen.split(' ')[1] || 'w');
        try {
            sfWorker.postMessage('position fen ' + fen);
            sfWorker.postMessage('go depth ' + EVAL_DEPTH);
        } catch (e) {}
    }

    function scheduleEvaluation(fen) {
        if (!fen || fen === lastEvaluatedFEN) return;
        lastEvaluatedFEN = fen;
        if (evalTimer) {
            clearTimeout(evalTimer);
            evalTimer = null;
        }
        evalTimer = setTimeout(function() {
            evaluateFEN(fen);
        }, 250);
    }

    function cpToWhitePercent(cp) {
        const capped = Math.max(-EVAL_MAX_CP, Math.min(EVAL_MAX_CP, cp));
        return 50 + (capped / (2 * EVAL_MAX_CP)) * 100;
    }

    function setEvalBar(whitePercent) {
        const w = document.getElementById('eval-white');
        const b = document.getElementById('eval-black');
        if (!w || !b) return;
        const p = Math.max(0, Math.min(100, whitePercent));
        w.style.width = p + '%';
        b.style.width = (100 - p) + '%';
        w.style.transition = 'width 1s linear';
        b.style.transition = 'width 1s linear';
    }

		function resetForNewGame() {
			if (eventSource) {
				try { eventSource.close(); } catch (e) {}
				eventSource = null;
			}
			whiteTime = 0;
			blackTime = 0;
			whiteCost = 0;
			blackCost = 0;
			turn = 'white';
			moveRetryCount = 0;

			const whiteTimeEl = document.getElementById('white-time');
			const blackTimeEl = document.getElementById('black-time');
			const whiteCostEl = document.getElementById('white-cost');
			const blackCostEl = document.getElementById('black-cost');
			if (whiteTimeEl) whiteTimeEl.textContent = '0.00s';
			if (blackTimeEl) blackTimeEl.textContent = '0.00s';
			if (whiteCostEl) whiteCostEl.textContent = '$0.0000';
			if (blackCostEl) blackCostEl.textContent = '$0.0000';

			const whitePanel = document.getElementById('white-panel');
			const blackPanel = document.getElementById('black-panel');
			if (whitePanel) whitePanel.classList.remove('ring-2', 'ring-green-500', 'shadow-lg');
			if (blackPanel) blackPanel.classList.remove('ring-2', 'ring-green-500', 'shadow-lg');

			winnerContainer.style.display = 'none';
			winnerText.textContent = '';
			winnerReason.textContent = '';

			// Reset move history placeholders
			const whiteMoves = document.getElementById('white-moves');
			const blackMoves = document.getElementById('black-moves');
			if (whiteMoves) whiteMoves.innerHTML = '<p class="text-gray-400 dark:text-gray-500 italic h-full flex items-center justify-center">Waiting for game to start...</p>';
			if (blackMoves) blackMoves.innerHTML = '<p class="text-gray-400 dark:text-gray-500 italic h-full flex items-center justify-center">Waiting for game to start...</p>';

			// Reset board to initial position
			updateBoard('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
		}

    async function fetchWithRetry(url, options, retries = 3, delay = 500) {
        for (let attempt = 0; attempt <= retries; attempt++) {
            try {
                const resp = await fetch(url, options);
                if (!resp.ok) {
                    throw new Error('HTTP ' + resp.status);
                }
                return resp;
            } catch (err) {
                if (attempt === retries) throw err;
                const backoff = delay * Math.pow(2, attempt);
                await new Promise(r => setTimeout(r, backoff));
            }
        }
    }

    window.addEventListener('offline', () => {
        isOffline = true;
    });
    window.addEventListener('online', () => {
        isOffline = false;
        resyncState();
        if (isGameRunning) playNextMove();
    });

    function applyServerState(state) {
        if (!state) return;
        try {
            updateBoard(state.fen);
            scheduleEvaluation(state.fen);
            highlightFromFEN(state.fen);
        } catch (e) {}

        whiteTime = state.white_time || 0;
        blackTime = state.black_time || 0;
        whiteCost = state.white_cost || 0;
        blackCost = state.black_cost || 0;
        const wt = document.getElementById('white-time');
        const bt = document.getElementById('black-time');
        const wc = document.getElementById('white-cost');
        const bc = document.getElementById('black-cost');
        if (wt) wt.textContent = `${whiteTime.toFixed(2)}s`;
        if (bt) bt.textContent = `${blackTime.toFixed(2)}s`;
        if (wc) wc.textContent = `$${whiteCost.toFixed(4)}`;
        if (bc) bc.textContent = `$${blackCost.toFixed(4)}`;

        rebuildMoveHistory(Array.isArray(state.moves) ? state.moves : []);

        if (state.is_over) {
            const result = state.result;
            const termination = state.termination || '';
            const whiteName = whiteDisplayName || "White";
            const blackName = blackDisplayName || "Black";

            if (termination === 'No response from the model.') {
                winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game canceled.</strong> Match canceled due to no response.`;
                if (winnerReason) winnerReason.textContent = termination;
                winnerContainer.style.display = 'block';
                isGameRunning = false;
                startButton.disabled = false;
                return;
            }
            if (result === '1-0') {
                winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game over!</strong> <span class="text-green-600 dark:text-green-400 font-semibold">${whiteName}</span> <span class="text-black dark:text-gray-100">won against</span> <span class="text-red-600 dark:text-red-400 font-semibold">${blackName}</span>`;
            } else if (result === '0-1') {
                winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game over!</strong> <span class="text-green-600 dark:text-green-400 font-semibold">${blackName}</span> <span class="text-black dark:text-gray-100">won against</span> <span class="text-red-600 dark:text-red-400 font-semibold">${whiteName}</span>`;
            } else {
                winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game over!</strong> Draw between ${whiteName} and ${blackName}`;
            }
            if (winnerReason) winnerReason.textContent = termination || '';
            winnerContainer.style.display = 'block';
            isGameRunning = false;
            startButton.disabled = false;
        }
    }

    function rebuildMoveHistory(moves) {
        const whiteContainer = document.getElementById('white-moves');
        const blackContainer = document.getElementById('black-moves');
        if (!whiteContainer || !blackContainer) return;
        whiteContainer.innerHTML = '';
        blackContainer.innerHTML = '';

        const elementsByColor = { white: [], black: [] };

        function createMoveElement(m) {
            const moveDiv = document.createElement('div');
            const mv = m.move || {};
            let moveText = '';
            if (typeof mv === 'string') {
                moveText = mv;
            } else {
                moveText = (mv.uci || mv.san || '');
            }
            moveDiv.innerHTML = `
                <p class="font-mono text-gray-800 dark:text-gray-200 font-bold">${m.move_number}. ${moveText}</p>
                <p class="text-gray-500 dark:text-gray-400 italic text-xs break-words">${m.rationale || ''}</p>
            `;
            return moveDiv;
        }

        (moves || []).forEach(m => {
            const colorLower = (m.color || '').toString().toLowerCase();
            const key = colorLower === 'white' ? 'white' : (colorLower === 'black' ? 'black' : 'white');
            elementsByColor[key].push(createMoveElement(m));
        });

        // Newest at top, highlight the last move for each color
        ['white', 'black'].forEach(key => {
            const container = key === 'white' ? whiteContainer : blackContainer;
            const list = elementsByColor[key];
            list.forEach(el => container.prepend(el));
            const last = container.querySelector('div');
            if (last) last.classList.add('last-move', 'font-bold');
        });
    }

		form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (isGameRunning) {
            return;
        }

        const whitePlayer = form.elements.white_player.value;
        const blackPlayer = form.elements.black_player.value;

        // Capture chosen display names for later use
        const whiteNameEl = document.querySelector('#white-panel .player-name');
        const blackNameEl = document.querySelector('#black-panel .player-name');
        whiteDisplayName = whiteNameEl ? whiteNameEl.textContent : '';
        blackDisplayName = blackNameEl ? blackNameEl.textContent : '';

        if (!whitePlayer || !blackPlayer || whitePlayer === blackPlayer) {
            alert('Please select two different opponents.');
            return;
        }

			// Fully reset game state and UI
			resetForNewGame();
        
        startButton.disabled = true;
        isGameRunning = true;

        try {
            const response = await fetchWithRetry('/api/start_game', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    white_player: whitePlayer,
                    black_player: blackPlayer
                })
            }, 2, 400);

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }
            
            gameId = data.game_id;
            highlightCurrentPlayer();
            openEventStream();
            playNextMove();

        } catch (error) {
            console.error('Error starting game:', error);
            winnerText.textContent = 'Error starting game. Please try again.';
            winnerText.style.display = 'block';
            startButton.disabled = false;
            isGameRunning = false;
        }
    });

    async function playNextMove() {
        if (!gameId || !isGameRunning) return;
        if (isOffline) {
            setTimeout(playNextMove, 1000);
            return;
        }

        try {
            const response = await fetchWithRetry(`/api/play_move/${gameId}`, {
                method: 'POST'
            }, 5, 300);

            const gameData = await response.json();

            if (!gameData) {
                await resyncState();
                if (isGameRunning) setTimeout(playNextMove, 500);
                return;
            }

            if (gameData.error) {
                const msg = gameData.details || gameData.error || 'Unknown error';
                console.error('Game error:', msg);
                winnerText.textContent = `Error: ${msg}`;
                winnerContainer.style.display = 'block';
                isGameRunning = false;
                startButton.disabled = false;
                return;
            }

            // Simplify: always resync from authoritative server state
            moveRetryCount = 0;
            await resyncState();
            if (isGameRunning) setTimeout(playNextMove, 500);
        } catch (err) {
            console.error('Network error during move, will retry:', err);
            moveRetryCount += 1;
            const backoff = Math.min(10000, 500 * Math.pow(2, moveRetryCount - 1));
            setTimeout(() => {
                if (isGameRunning) playNextMove();
            }, backoff);
            resyncState();
        }
    }

    function openEventStream() {
        if (!gameId) return;
        try {
            if (eventSource) { try { eventSource.close(); } catch (e) {} }
            eventSource = new EventSource(`/api/stream/${gameId}?ts=${Date.now()}`);
            eventSource.addEventListener('state', (evt) => {
                try {
                    const state = JSON.parse(evt.data);
                    applyServerState(state);
                } catch (e) {}
            });
            eventSource.addEventListener('ping', () => {});
            eventSource.onerror = () => {
                try { eventSource.close(); } catch (e) {}
                eventSource = null;
                if (isGameRunning) setTimeout(openEventStream, 1000);
            };
        } catch (e) {
            // Fallback to polling-only
        }
    }

    async function resyncState() {
        if (!gameId) return;
        try {
            const resp = await fetch(`/api/game/${gameId}?ts=${Date.now()}`, { cache: 'no-store' });
            if (!resp.ok) return;
            const state = await resp.json();
            if (!state) return;
            applyServerState(state);
        } catch (e) {
            // Ignore; we'll retry on the next loop
        }
    }

    function highlightCurrentPlayer() {
        if (turn === 'white') {
            document.getElementById('white-panel').classList.add('ring-2', 'ring-green-500', 'shadow-lg');
            document.getElementById('black-panel').classList.remove('ring-2', 'ring-green-500', 'shadow-lg');
        } else {
            document.getElementById('black-panel').classList.add('ring-2', 'ring-green-500', 'shadow-lg');
            document.getElementById('white-panel').classList.remove('ring-2', 'ring-green-500', 'shadow-lg');
        }
    }

    function highlightFromFEN(fen) {
        try {
            const parts = (fen || '').split(' ');
            const side = parts[1] === 'b' ? 'black' : 'white';
            document.getElementById('white-panel').classList.remove('ring-2', 'ring-green-500', 'shadow-lg');
            document.getElementById('black-panel').classList.remove('ring-2', 'ring-green-500', 'shadow-lg');
            if (side === 'white') {
                document.getElementById('white-panel').classList.add('ring-2', 'ring-green-500', 'shadow-lg');
            } else {
                document.getElementById('black-panel').classList.add('ring-2', 'ring-green-500', 'shadow-lg');
            }
        } catch (e) {}
    }

    function setupPlayerPanels() {
        const playerPanels = document.querySelectorAll('.player-panel');
        playerPanels.forEach(panel => {
            const selectorButton = panel.querySelector('.player-selector-button');
            const selectorList = panel.querySelector('.player-selector-list');
            const llmOptions = panel.querySelectorAll('.llm-option');
            const playerInput = panel.querySelector('.player-input');
            const playerName = panel.querySelector('.player-name');
            const playerInfo = panel.querySelector('.player-info');
            const playerAvatar = panel.querySelector('.player-avatar');

            selectorButton.addEventListener('click', () => {
                selectorList.classList.toggle('hidden');
            });

            llmOptions.forEach(option => {
                option.addEventListener('click', () => {
                    if (option.dataset.deactivated === 'true') {
                        return;
                    }
                    const llmId = option.dataset.llmId;
                    
                    // Disable option in other panel
                    const otherPanel = [...playerPanels].find(p => p !== panel);
                    otherPanel.querySelectorAll('.llm-option').forEach(opt => {
                        if (opt.dataset.llmId === llmId) {
                            opt.classList.add('text-gray-400', 'dark:text-zinc-600', 'cursor-not-allowed');
                            opt.classList.remove('text-gray-900', 'dark:text-gray-100', 'hover:bg-indigo-600', 'hover:text-white');
                        } else {
                            // Respect deactivated styling if present
                            opt.classList.remove('cursor-not-allowed');
                            if (opt.dataset.deactivated === 'true') {
                                opt.classList.add('text-gray-400', 'dark:text-zinc-500', 'cursor-not-allowed');
                                opt.classList.remove('text-gray-900', 'dark:text-gray-100');
                            } else {
                                opt.classList.remove('text-gray-400', 'dark:text-zinc-500', 'dark:text-zinc-600');
                                opt.classList.add('text-gray-900', 'dark:text-gray-100', 'hover:bg-indigo-600', 'hover:text-white');
                            }
                        }
                    });

                    playerInput.value = llmId;
                    playerName.textContent = option.dataset.llmName;
                    playerInfo.textContent = `${option.dataset.llmProvider} | ${option.dataset.llmElo} ELO`;
					
					const svgEl = option.querySelector('svg');
					if (svgEl) {
						playerAvatar.innerHTML = svgEl.outerHTML;
					} else {
						const iconWrapper = option.querySelector('.w-6.h-6');
						playerAvatar.innerHTML = iconWrapper ? iconWrapper.innerHTML : '';
					}
                    playerAvatar.classList.remove('bg-gray-200', 'dark:bg-zinc-800', 'border-2', 'border-dashed', 'border-gray-300', 'dark:border-zinc-700');

                    selectorList.classList.add('hidden');
                });
            });
        });

        document.addEventListener('click', (e) => {
            playerPanels.forEach(panel => {
                if (!panel.contains(e.target)) {
                    panel.querySelector('.player-selector-list').classList.add('hidden');
                }
            });
        });
    }

    function fenToBoard(fen) {
        const board = [];
        const rows = fen.split(' ')[0].split('/');
        for (const row of rows) {
            const boardRow = [];
            for (const char of row) {
                if (isNaN(parseInt(char))) {
                    boardRow.push(char);
                } else {
                    for (let i = 0; i < parseInt(char); i++) {
                        boardRow.push('');
                    }
                }
            }
            board.push(boardRow);
        }
        return board;
    }

    function updateBoard(fen) {
        const board = fenToBoard(fen);
        const chessboard = document.getElementById('chessboard');
        const squares = chessboard.querySelectorAll('.flex.items-center.justify-center');

        board.flat().forEach((piece, index) => {
            const pieceImg = squares[index].querySelector('img.piece-img');
            if (!pieceImg) return;
            if (piece) {
                const colorCode = piece === piece.toUpperCase() ? 'w' : 'b';
                const typeCode = piece.toUpperCase();
                pieceImg.src = `/static/pieces/${colorCode}${typeCode}.svg?v=2`;
            } else {
                pieceImg.removeAttribute('src');
            }
        });
    }

    function updateStats(gameData) {
        if (gameData.color === 'white') {
            whiteTime += gameData.latency;
            whiteCost += gameData.cost;
            document.getElementById('white-time').textContent = `${whiteTime.toFixed(2)}s`;
            document.getElementById('white-cost').textContent = `$${whiteCost.toFixed(4)}`;
        } else {
            blackTime += gameData.latency;
            blackCost += gameData.cost;
            document.getElementById('black-time').textContent = `${blackTime.toFixed(2)}s`;
            document.getElementById('black-cost').textContent = `$${blackCost.toFixed(4)}`;
        }
    }

    function updateMoveHistory(gameData) {
        const moveHistoryContainer = document.getElementById(`${gameData.color}-moves`);
        
        // Clear the "Waiting for game to start..." message on the first move
        const initialMessage = moveHistoryContainer.querySelector('p');
        if (initialMessage && /Waiting for game to start/.test(initialMessage.innerText)) {
            moveHistoryContainer.innerHTML = '';
        }

        // Un-highlight the previous move and add a separator
        const lastMove = moveHistoryContainer.querySelector('.last-move');
        if (lastMove) {
            lastMove.classList.remove('last-move', 'font-bold');
            lastMove.classList.add('pt-3', 'mt-3', 'border-t', 'border-gray-200', 'dark:border-zinc-700');
        }
        
        const moveElement = document.createElement('div');
        // Add a class to identify the last move for highlighting
        moveElement.classList.add('last-move', 'font-bold'); 
        const moveText = gameData.move_uci || gameData.move_san || '';
        moveElement.innerHTML = `
            <p class="font-mono text-gray-800 dark:text-gray-200 font-bold">${gameData.move_number}. ${moveText}</p>
            <p class="text-gray-500 dark:text-gray-400 italic text-xs break-words">${gameData.rationale}</p>
        `;
        
        moveHistoryContainer.prepend(moveElement);
    }

    setupPlayerPanels();
    initStockfish();
});
