document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('start-game-form');
    const startButton = document.getElementById('start-battle-btn');
    const winnerText = document.getElementById('winner-text');
    let gameId = null;
    let isGameRunning = false;

    let whiteTime = 0;
    let blackTime = 0;
    let whiteCost = 0;
    let blackCost = 0;
    let turn = 'white';

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        if (isGameRunning) {
            return;
        }

        const whitePlayer = form.elements.white_player.value;
        const blackPlayer = form.elements.black_player.value;

        if (!whitePlayer || !blackPlayer || whitePlayer === blackPlayer) {
            alert('Please select two different opponents.');
            return;
        }

        // Reset UI
        winnerText.style.display = 'none';
        document.getElementById('white-moves').innerHTML = '<p class="text-gray-400 dark:text-gray-500 italic h-full flex items-center justify-center">Waiting for game to start...</p>';
        document.getElementById('black-moves').innerHTML = '<p class="text-gray-400 dark:text-gray-500 italic h-full flex items-center justify-center">Waiting for game to start...</p>';
        
        startButton.disabled = true;
        isGameRunning = true;

        try {
            const response = await fetch('/api/start_game', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    white_player: whitePlayer,
                    black_player: blackPlayer
                })
            });

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
            const response = await fetch(`/api/play_move/${gameId}`, {
                method: 'POST'
            });

            const gameData = await response.json();

            if (gameData.error) {
                console.error('Game error:', gameData.details);
                winnerText.textContent = `Error: ${gameData.details}`;
                winnerText.style.display = 'block';
                isGameRunning = false;
                startButton.disabled = false;
                return;
            }

            if (gameData.is_over) {
                winnerText.textContent = `Game Over: ${gameData.result} (${gameData.termination})`;
                winnerText.style.display = 'block';
                isGameRunning = false;
                startButton.disabled = false;
                document.getElementById('white-panel').classList.remove('ring-2', 'ring-indigo-500', 'shadow-lg');
                document.getElementById('black-panel').classList.remove('ring-2', 'ring-indigo-500', 'shadow-lg');
                if (gameData.fen) {
                    updateBoard(gameData.fen);
                    updateStats(gameData);
                    updateMoveHistory(gameData);
                }
            } else if (gameData.status === 'success') {
                updateBoard(gameData.fen);
                updateStats(gameData);
                updateMoveHistory(gameData);
                turn = turn === 'white' ? 'black' : 'white';
                highlightCurrentPlayer();
                setTimeout(playNextMove, 500); // Wait 500ms before next move
            }
        } catch (err) {
            console.error('Error during move:', err);
            winnerText.textContent = 'Connection error. Please try again.';
            winnerText.style.display = 'block';
            isGameRunning = false;
            startButton.disabled = false;
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
                    
                    playerAvatar.innerHTML = option.querySelector('svg').outerHTML;
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
            <p class="font-mono text-gray-800 dark:text-gray-200 font-bold">${gameData.move_san}</p>
            <p class="text-gray-500 dark:text-gray-400 italic text-xs break-words">"${gameData.rationale}"</p>
        `;
        
        moveHistoryContainer.prepend(moveElement);
    }

    setupPlayerPanels();
});
