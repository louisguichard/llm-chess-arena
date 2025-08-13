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

		function resetForNewGame() {
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
                return await fetch(url, options);
            } catch (err) {
                if (attempt === retries) throw err;
                const backoff = delay * Math.pow(2, attempt);
                await new Promise(r => setTimeout(r, backoff));
            }
        }
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
        if (!gameId) return;

        try {
            const response = await fetchWithRetry(`/api/play_move/${gameId}`, {
                method: 'POST'
            }, 5, 300);

            const gameData = await response.json();

            if (gameData.error) {
                const msg = gameData.details || gameData.error || 'Unknown error';
                console.error('Game error:', msg);
                winnerText.textContent = `Error: ${msg}`;
                winnerContainer.style.display = 'block';
                isGameRunning = false;
                startButton.disabled = false;
                return;
            }

            if (gameData.status === "game_over") {
                const result = gameData.result;
                const whiteName = whiteDisplayName || "White";
                const blackName = blackDisplayName || "Black";
                if (result === '1-0') {
                    winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game over!</strong> <span class="text-green-600 dark:text-green-400 font-semibold">${whiteName}</span> <span class="text-black dark:text-gray-100">won against</span> <span class="text-red-600 dark:text-red-400 font-semibold">${blackName}</span>`;
                } else if (result === '0-1') {
                    winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game over!</strong> <span class="text-green-600 dark:text-green-400 font-semibold">${blackName}</span> <span class="text-black dark:text-gray-100">won against</span> <span class="text-red-600 dark:text-red-400 font-semibold">${whiteName}</span>`;
                } else {
                    winnerText.innerHTML = `<strong class="text-black dark:text-gray-100">Game over!</strong> Draw between ${whiteName} and ${blackName}`;
                }
                winnerContainer.style.display = 'block';
                isGameRunning = false;
                startButton.disabled = false;
                return
            }

            if (gameData.is_over) {
                // Last move played, UI is updated, then the game truly ends.
                updateBoard(gameData.fen);
                updateStats(gameData);
                updateMoveHistory(gameData);
                highlightCurrentPlayer(); // Un-highlight current player
                setTimeout(playNextMove, 500);

            } else if (gameData.status === 'success') {
                moveRetryCount = 0;
                updateBoard(gameData.fen);
                updateStats(gameData);
                updateMoveHistory(gameData);
                turn = turn === 'white' ? 'black' : 'white';
                highlightCurrentPlayer();
                setTimeout(playNextMove, 500); // Wait 500ms before next move
            }
        } catch (err) {
            console.error('Network error during move, will retry:', err);
            // Exponential backoff up to ~10s
            moveRetryCount += 1;
            const backoff = Math.min(10000, 500 * Math.pow(2, moveRetryCount - 1));
            setTimeout(() => {
                if (isGameRunning) playNextMove();
            }, backoff);
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
                    const llmId = option.dataset.llmId;
                    
                    // Disable option in other panel
                    const otherPanel = [...playerPanels].find(p => p !== panel);
                    otherPanel.querySelectorAll('.llm-option').forEach(opt => {
                        if (opt.dataset.llmId === llmId) {
                            opt.classList.add('text-gray-400', 'dark:text-zinc-600', 'cursor-not-allowed');
                            opt.classList.remove('text-gray-900', 'dark:text-gray-100', 'hover:bg-indigo-600', 'hover:text-white');
                        } else {
                            opt.classList.remove('text-gray-400', 'dark:text-zinc-600', 'cursor-not-allowed');
                            opt.classList.add('text-gray-900', 'dark:text-gray-100', 'hover:bg-indigo-600', 'hover:text-white');
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
        if (turn === 'white') {
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
        const moveHistoryContainer = document.getElementById(`${turn}-moves`);
        
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
        moveElement.innerHTML = `
            <p class="font-mono text-gray-800 dark:text-gray-200 font-bold">${gameData.move_number}. ${gameData.move_san}</p>
            <p class="text-gray-500 dark:text-gray-400 italic text-xs break-words">${gameData.rationale}</p>
        `;
        
        moveHistoryContainer.prepend(moveElement);
    }

    setupPlayerPanels();
});
