// --- MOCK DATA (to be replaced with API calls) ---
const initialBoard = [
  ['r', 'n', 'b', 'q', 'k', 'b', 'n', 'r'],
  ['p', 'p', 'p', 'p', 'p', 'p', 'p', 'p'],
  ['', '', '', '', '', '', '', ''],
  ['', '', '', '', '', '', '', ''],
  ['', '', '', '', '', '', '', ''],
  ['', '', '', '', '', '', '', ''],
  ['P', 'P', 'P', 'P', 'P', 'P', 'P', 'P'],
  ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'],
];

const PIECE_UNICODE = {
  'p': '♟︎', 'r': '♜', 'n': '♞', 'b': '♝', 'q': '♛', 'k': '♚',
  'P': '♙', 'R': '♖', 'N': '♘', 'B': '♗', 'Q': '♕', 'K': '♔',
};

// --- STATE MANAGEMENT ---
const state = {
  theme: 'light',
  activePage: 'battle',
  llms: [],
  leaderboardData: [],
  llm1: null,
  llm2: null,
  gameStatus: 'idle', // 'idle' | 'playing' | 'finished'
  board: initialBoard,
  moves: [],
  player1Stats: { time: 0, cost: 0 },
  player2Stats: { time: 0, cost: 0 },
  turn: 'white',
  winner: null,
  eventSource: null,
};

// --- RENDER FUNCTIONS ---

function render() {
  const app = document.getElementById('app');
  app.innerHTML = '';
  app.appendChild(LLMChessArenaPage());
  updateTheme();
}

function updateTheme() {
    document.documentElement.classList.remove('dark');
    state.theme = 'light';
    localStorage.setItem('theme', 'light');
}

function toggleTheme() {
    state.theme = state.theme === 'light' ? 'dark' : 'light';
    render();
}

function setActivePage(page) {
    state.activePage = page;
    render();
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

function handleStartBattle() {
    if (!state.llm1 || !state.llm2 || state.llm1.id === state.llm2.id) {
        alert("Please select two different opponents.");
        return;
    }

    // Close any previous SSE connection before starting a new one
    if (state.eventSource) {
        try { state.eventSource.close(); } catch (_) {}
        state.eventSource = null;
    }

    state.gameStatus = 'playing';
    state.moves = [];
    state.board = initialBoard;
    state.player1Stats = { time: 0, cost: 0 };
    state.player2Stats = { time: 0, cost: 0 };
    state.turn = 'white';
    state.winner = null;
    render();

    const params = new URLSearchParams({
        white_player: state.llm1.id,
        black_player: state.llm2.id,
    });
    const eventSource = new EventSource(`/api/start_game?${params.toString()}`);
    state.eventSource = eventSource;

    eventSource.onmessage = function(event) {
        const gameData = JSON.parse(event.data);

        // Handle server-sent error payloads gracefully
        if (gameData.error) {
            console.error("Game error:", gameData);
            eventSource.close();
            state.gameStatus = 'finished';
            // Ratings may have been updated server-side already
            fetchLeaderboard();
            render();
            return;
        }

        if (gameData.is_over) {
            state.gameStatus = 'finished';
            state.winner = getWinnerText(gameData.result, gameData.termination);
            eventSource.close();
            // Fetch new ratings after game is over
            fetchLeaderboard();
        } else if (gameData.status === 'success') {
            const newMove = {
                player: state.turn === 'white' ? state.llm1.name : state.llm2.name,
                notation: gameData.move_san,
                reasoning: gameData.rationale,
            };
            state.moves.push(newMove);

            if (state.turn === 'white') {
                state.player1Stats.cost += gameData.cost;
                state.player1Stats.time += gameData.latency;
            } else {
                state.player2Stats.cost += gameData.cost;
                state.player2Stats.time += gameData.latency;
            }

            state.turn = state.turn === 'white' ? 'black' : 'white';
            state.board = fenToBoard(gameData.fen);
        }
        
        render();
    };

    // No heartbeat events; server streams each move when ready.

    eventSource.onerror = function(err) {
        console.warn(
            "EventSource connection error. The browser will attempt to reconnect.",
            err
        );

        // The EventSource API includes a built-in reconnection mechanism.
        // We will only intervene if the connection is permanently closed.
        if (eventSource.readyState === EventSource.CLOSED) {
            console.error("EventSource connection has been permanently closed.");
            if (state.gameStatus === "playing") {
                state.gameStatus = "finished";
                state.winner = "Aborted due to connection error";
                render();
            }
        }
    };
}

function getWinnerText(result, termination) {
    if (result === "1-0") {
        return `White wins by ${termination}`;
    }
    if (result === "0-1") {
        return `Black wins by ${termination}`;
    }
    return `Draw by ${termination}`;
}

// --- COMPONENTS ---

function LeaderboardPage() {
    const container = document.createElement('div');
    container.className = "max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8";
    container.innerHTML = `
        <div class="flex items-center gap-3 mb-6">
            <svg class="w-8 h-8 text-amber-500" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg>
            <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Leaderboard</h1>
        </div>
        <p class="mb-4 text-sm text-gray-600 dark:text-gray-400">More models coming soon.</p>
        <div class="bg-white dark:bg-zinc-900 rounded-xl border border-gray-200 dark:border-zinc-700 shadow-sm overflow-hidden">
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead>
                        <tr class="border-b border-gray-200 dark:border-zinc-700 bg-gray-50 dark:bg-zinc-800/50">
                            <th class="px-4 py-4 text-center font-semibold text-sm text-gray-600 dark:text-gray-300">#</th>
                            <th class="px-4 py-4 text-left font-semibold text-sm text-gray-600 dark:text-gray-300">Player</th>
                            <th class="px-4 py-4 text-right font-semibold text-sm text-gray-600 dark:text-gray-300">ELO</th>
                            <th class="px-4 py-4 text-center font-semibold text-sm text-gray-600 dark:text-gray-300">Games</th>
                            <th class="px-4 py-4 text-center font-semibold text-sm text-gray-600 dark:text-gray-300">W / D / L</th>
                            <th class="px-4 py-4 text-center font-semibold text-sm text-gray-600 dark:text-gray-300">Win %</th>
                            <th class="px-4 py-4 text-center font-semibold text-sm text-gray-600 dark:text-gray-300">Time/Move</th>
                            <th class="px-4 py-4 text-center font-semibold text-sm text-gray-600 dark:text-gray-300">Cost/Move</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.leaderboardData.map((llm, index) => `
                            <tr class="border-b border-gray-200 dark:border-zinc-800 last:border-b-0 hover:bg-gray-50 dark:hover:bg-zinc-800/50 transition-colors">
                                <td class="px-4 py-4 text-center font-medium text-gray-500 dark:text-gray-400">${index + 1}</td>
                                <td class="px-4 py-4">
                                    <div class="flex items-center">
                                        <div class="w-10 h-10 mr-3 flex-shrink-0">${llm.avatar}</div>
                                        <div>
                                            <p class="font-semibold text-gray-900 dark:text-gray-100">${llm.name}</p>
                                            <p class="text-sm text-gray-500 dark:text-gray-400">${llm.provider}</p>
                                        </div>
                                    </div>
                                </td>
                                <td class="px-4 py-4 text-right font-mono text-lg font-semibold text-gray-800 dark:text-gray-200">${llm.elo}</td>
                                <td class="px-4 py-4 text-center font-mono text-gray-600 dark:text-gray-300">${llm.matchesPlayed}</td>
                                <td class="px-4 py-4 text-center font-mono text-sm">
                                    ${llm.matchesPlayed > 0 ? `
                                        <span class="text-green-600 dark:text-green-400">${llm.wins}</span> / 
                                        <span class="text-yellow-600 dark:text-yellow-400">${llm.draws}</span> / 
                                        <span class="text-red-600 dark:text-red-400">${llm.losses}</span>
                                    ` : `<span class="text-gray-400 dark:text-gray-500">-</span>`}
                                </td>
                                <td class="px-4 py-4 text-center font-mono text-gray-600 dark:text-gray-300">
                                    ${llm.matchesPlayed > 0 ? `${llm.winRate}%` : `-`}
                                </td>
                                <td class="px-4 py-4 text-center font-mono text-gray-600 dark:text-gray-300">
                                    ${llm.moves > 0 ? `${llm.avgTimePerMove.toFixed(1)}s` : `-`}
                                </td>
                                <td class="px-4 py-4 text-center font-mono text-gray-600 dark:text-gray-300">
                                    ${llm.moves > 0 ? `$${llm.avgCostPerMove.toFixed(4)}` : `-`}
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
    return container;
}

function BattlePage() {
    const container = document.createElement('div');
    container.className = "max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8";
    container.innerHTML = `
        <div class="grid grid-cols-1 xl:grid-cols-7 gap-6 lg:gap-8">
            <div class="xl:col-span-2" id="player1-panel"></div>
            <div class="xl:col-span-3 flex flex-col items-center gap-4">
                <div id="chessboard-container" class="w-full"></div>
                <div class="text-center">
                    <button id="start-battle-btn" class="w-auto flex items-center justify-center gap-2 bg-indigo-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-indigo-700 disabled:bg-blue-900/50 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors">
                        <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg>
                        <span>Start Battle</span>
                    </button>
                    <p id="winner-text" class="mt-3 font-semibold text-green-600 dark:text-green-400" style="display: none;"></p>
                </div>
            </div>
            <div class="xl:col-span-2" id="player2-panel"></div>
        </div>
    `;

    if (state.gameStatus === 'finished' && state.winner) {
        const winnerText = container.querySelector('#winner-text');
        winnerText.textContent = `Winner: ${state.winner}!`;
        winnerText.style.display = 'block';
    }

    container.querySelector('#player1-panel').appendChild(PlayerInfoPanel({ player: state.llm1, onSelectPlayer: (llm) => { state.llm1 = llm; render(); }, availableLLMs: state.llms, opponentLLM: state.llm2, time: state.player1Stats.time, cost: state.player1Stats.cost, moves: state.moves.filter(m => m.player === state.llm1?.name), isThinking: state.gameStatus === 'playing' && state.turn === 'white', isGameInProgress: state.gameStatus === 'playing' }));
    container.querySelector('#player2-panel').appendChild(PlayerInfoPanel({ player: state.llm2, onSelectPlayer: (llm) => { state.llm2 = llm; render(); }, availableLLMs: state.llms, opponentLLM: state.llm1, time: state.player2Stats.time, cost: state.player2Stats.cost, moves: state.moves.filter(m => m.player === state.llm2?.name), isThinking: state.gameStatus === 'playing' && state.turn === 'black', isGameInProgress: state.gameStatus === 'playing' }));
    container.querySelector('#chessboard-container').appendChild(Chessboard({ board: state.board }));
    container.querySelector('#start-battle-btn').addEventListener('click', handleStartBattle);

    return container;
}

function PlayerInfoPanel({ player, onSelectPlayer, availableLLMs, opponentLLM, time, cost, moves, isThinking, isGameInProgress }) {
    const container = document.createElement('div');
    container.className = `bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-700 rounded-xl p-4 md:p-6 flex flex-col h-full transition-all duration-300 ${isThinking ? 'ring-2 ring-indigo-500 shadow-lg' : ''}`;
    
    let isSelectorOpen = false;

    const selectorId = `player-selector-${player?.id || Math.random()}`;

    function toggleSelector() {
        isSelectorOpen = !isSelectorOpen;
        const selectorList = container.querySelector('.player-selector-list');
        if (isSelectorOpen) {
            selectorList.classList.remove('hidden');
        } else {
            selectorList.classList.add('hidden');
        }
    }

    const selectorHTML = `
        <div class="relative mb-4">
            <button class="player-selector-button w-full flex items-center text-left p-2 -m-2 rounded-lg transition-colors hover:bg-gray-100 dark:hover:bg-zinc-800/80 disabled:cursor-not-allowed disabled:hover:bg-transparent" ${isGameInProgress ? 'disabled' : ''}>
                ${player ? `
                    <div class="w-12 h-12 mr-4 flex-shrink-0">${player.avatar}</div>
                    <div class="flex-grow">
                        <h3 class="font-bold text-lg text-gray-900 dark:text-gray-100">${player.name}</h3>
                        <p class="text-sm text-gray-500 dark:text-gray-400">${player.provider} | ${player.elo} ELO</p>
                    </div>
                ` : `
                    <div class="flex items-center w-full">
                        <div class="bg-gray-200 dark:bg-zinc-800 border-2 border-dashed border-gray-300 dark:border-zinc-700 rounded-full w-12 h-12 mr-4 flex-shrink-0"></div>
                        <div class="flex-grow">
                            <h3 class="font-bold text-lg text-gray-500 dark:text-gray-400">Select Player</h3>
                            <p class="text-sm text-gray-500 dark:text-gray-400">Click to choose an LLM</p>
                        </div>
                    </div>
                `}
                ${!isGameInProgress ? `<svg class="h-5 w-5 text-gray-400 ml-auto transition-transform ${isSelectorOpen ? 'rotate-180' : ''}" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>` : ''}
            </button>
            <ul class="player-selector-list hidden absolute z-10 mt-2 w-full bg-white dark:bg-zinc-800 shadow-lg max-h-60 rounded-md py-1 text-base ring-1 ring-black ring-opacity-5 overflow-auto focus:outline-none sm:text-sm">
                ${availableLLMs.map(llm => `
                    <li data-llm-id="${llm.id}" class="llm-option cursor-pointer select-none relative py-2 pl-3 pr-9 ${llm.id === opponentLLM?.id ? 'text-gray-400 dark:text-zinc-600 cursor-not-allowed' : 'text-gray-900 dark:text-gray-100 hover:bg-indigo-600 hover:text-white'}">
                        <span class="flex items-center">
                            <div class="w-6 h-6 mr-2 flex-shrink-0">${llm.avatar}</div>
                            <span class="font-normal block truncate">${llm.name}</span>
                        </span>
                        ${player?.id === llm.id ? `
                            <span class="text-indigo-600 absolute inset-y-0 right-0 flex items-center pr-4">
                                <svg class="h-5 w-5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                            </span>
                        ` : ''}
                    </li>
                `).join('')}
            </ul>
        </div>
    `;
    
    container.innerHTML = selectorHTML + `
        <div class="border-t border-gray-200 dark:border-zinc-700 pt-4 flex flex-col flex-grow">
            <div class="grid grid-cols-2 gap-4 mb-4 text-center">
                <div class="bg-gray-100 dark:bg-zinc-800 p-2 rounded-lg">
                    <div class="flex items-center justify-center text-gray-500 dark:text-gray-400 text-xs sm:text-sm"><svg class="w-4 h-4 mr-1.5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg> Time</div>
                    <div class="font-mono text-lg text-gray-900 dark:text-gray-100">${time.toFixed(2)}s</div>
                </div>
                <div class="bg-gray-100 dark:bg-zinc-800 p-2 rounded-lg">
                    <div class="flex items-center justify-center text-gray-500 dark:text-gray-400 text-xs sm:text-sm"><svg class="w-4 h-4 mr-1.5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg> Cost</div>
                    <div class="font-mono text-lg text-gray-900 dark:text-gray-100">$${cost.toFixed(4)}</div>
                </div>
            </div>
            <div class="flex-grow min-h-0 flex flex-col">
                <h4 class="text-sm font-semibold mb-2 text-gray-800 dark:text-gray-200">Move History & Reasoning</h4>
                <div class="bg-gray-50 dark:bg-zinc-800/50 rounded-lg p-3 flex-grow overflow-y-auto space-y-3 text-sm" style="max-height: 300px;">
                    ${moves.length > 0 ? moves.slice().reverse().map((move, index) => `
                        <div class="${index !== 0 ? 'border-t border-gray-200 dark:border-zinc-700 pt-2' : ''}">
                            <p class="font-mono text-gray-800 dark:text-gray-200 ${index === 0 ? 'font-bold' : ''}">${move.notation}</p>
                            <p class="text-gray-500 dark:text-gray-400 italic text-xs break-words">"${move.reasoning}"</p>
                        </div>
                    `).join('') : '<p class="text-gray-400 dark:text-gray-500 italic h-full flex items-center justify-center">Waiting for game to start...</p>'}
                </div>
            </div>
        </div>
    `;
    
    container.querySelector('.player-selector-button').addEventListener('click', toggleSelector);
    container.querySelectorAll('.llm-option').forEach(option => {
        option.addEventListener('click', (e) => {
            const llmId = e.currentTarget.dataset.llmId;
            const selectedLlm = availableLLMs.find(llm => llm.id === llmId);
            if (selectedLlm && selectedLlm.id !== opponentLLM?.id) {
                onSelectPlayer(selectedLlm);
                toggleSelector(); // Close after selection
            }
        });
    });

    return container;
}

function Chessboard({ board }) {
    const container = document.createElement('div');
    container.className = "bg-white dark:bg-zinc-900 p-2 sm:p-3 rounded-xl border border-gray-200 dark:border-zinc-700 shadow-md";
    container.innerHTML = `
        <div class="aspect-square grid grid-cols-8 grid-rows-8 gap-0 overflow-hidden rounded-md">
            ${board.flat().map((piece, index) => {
                const row = Math.floor(index / 8);
                const col = index % 8;
                const isLight = (row + col) % 2 !== 0;
                const pieceColor = piece === piece.toUpperCase() ? 'text-gray-800 dark:text-gray-100' : 'text-zinc-500 dark:text-zinc-400';
                return `
                    <div class="flex items-center justify-center ${isLight ? 'bg-gray-200 dark:bg-zinc-600' : 'bg-green-700/80 dark:bg-green-900/80'}">
                        <span class="text-xl sm:text-3xl md:text-4xl ${pieceColor} select-none">
                            ${PIECE_UNICODE[piece] || ''}
                        </span>
                    </div>
                `;
            }).join('')}
        </div>
    `;
    return container;
}

function LLMChessArenaPage() {
    const container = document.createElement('div');
    container.className = "min-h-screen bg-gray-100 dark:bg-zinc-950 text-gray-900 dark:text-gray-100 font-sans";

    container.innerHTML = `
      <header class="sticky top-0 z-40 w-full backdrop-blur-sm bg-white/80 dark:bg-zinc-900/80 border-b border-gray-200 dark:border-zinc-800">
        <div class="max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8">
          <div class="flex items-center justify-between h-16">
            <div class="flex items-center space-x-2">
                <svg class="h-7 w-7 text-indigo-500" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a10 10 0 0 0-10 10c0 4.42 2.87 8.17 6.84 9.5.6.11.82-.26.82-.57 0-.28-.01-1.02-.01-2-2.82.61-3.42-1.34-3.42-1.34-.54-1.38-1.33-1.75-1.33-1.75-1.08-.74.08-.72.08-.72 1.2.08 1.82 1.23 1.82 1.23 1.07 1.83 2.8 1.3 3.48 1 .11-.78.42-1.3.76-1.6-2.66-.3-5.46-1.33-5.46-5.93 0-1.31.47-2.38 1.23-3.22-.12-.3-.54-1.52.12-3.18 0 0 1-.32 3.3 1.23.95-.26 1.98-.39 3-.4 1.02.01 2.05.14 3 .4 2.28-1.55 3.28-1.23 3.28-1.23.66 1.66.24 2.88.12 3.18.77.84 1.23 1.91 1.23 3.22 0 4.61-2.8 5.63-5.48 5.92.43.37.81 1.1.81 2.22 0 1.6-.02 2.89-.02 3.28 0 .31.22.69.83.57A10 10 0 0 0 22 12 10 10 0 0 0 12 2z"/></svg> <!-- Placeholder icon -->
                <span class="font-bold text-xl">LLM Chess Arena</span>
                <span class="ml-2 inline-flex items-center rounded-full bg-indigo-100 dark:bg-indigo-900/40 px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800">Preview</span>
            </div>
            <nav class="hidden md:flex items-center space-x-2">
              <button data-page="battle" class="nav-link px-3 py-2 rounded-md text-sm font-medium transition-colors ${state.activePage === 'battle' ? 'text-indigo-500' : 'text-gray-500 dark:text-gray-300 hover:text-indigo-500'}">Battle</button>
              <button data-page="leaderboard" class="nav-link px-3 py-2 rounded-md text-sm font-medium transition-colors ${state.activePage === 'leaderboard' ? 'text-indigo-500' : 'text-gray-500 dark:text-gray-300 hover:text-indigo-500'}">Leaderboard</button>
            </nav>
          </div>
        </div>
      </header>
      
      <main class="pb-16 md:pb-0">
          <!-- Page content will be injected here -->
      </main>

      <nav class="md:hidden fixed bottom-0 left-0 right-0 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-sm border-t border-gray-200 dark:border-zinc-800 p-2">
        <div class="flex justify-around">
           <button data-page="battle" class="mobile-nav-link flex flex-col items-center gap-1 p-2 rounded-lg w-full ${state.activePage === 'battle' ? 'text-indigo-500' : 'text-gray-500 dark:text-gray-400'}"> <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg> <span class="text-xs font-medium">Battle</span> </button>
           <button data-page="leaderboard" class="mobile-nav-link flex flex-col items-center gap-1 p-2 rounded-lg w-full ${state.activePage === 'leaderboard' ? 'text-indigo-500' : 'text-gray-500 dark:text-gray-400'}"> <svg class="w-5 h-5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"></path></svg> <span class="text-xs font-medium">Leaderboard</span> </button>
        </div>
      </nav>
    `;

    const mainContent = container.querySelector('main');
    if (state.activePage === 'battle') {
        mainContent.appendChild(BattlePage());
    } else {
        mainContent.appendChild(LeaderboardPage());
    }
    
    // Add event listeners
    // Theme toggle removed; forcing light mode
    container.querySelectorAll('.nav-link, .mobile-nav-link').forEach(link => {
        link.addEventListener('click', (e) => setActivePage(e.currentTarget.dataset.page));
    });

    return container;
}

async function fetchModels() {
    const response = await fetch('/api/models');
    const modelIds = await response.json();
    // For now, let's create mock LLM objects.
    // In the future, this could be enriched with more data.
    state.llms = modelIds.map(id => ({
        id: id,
        name: id.split('/')[1] || id,
        provider: id.split('/')[0] || 'Unknown',
        elo: 1200, // Default ELO
        avatar: `<div class="w-full h-full bg-gray-600 rounded-full flex items-center justify-center text-white font-bold text-lg">${(id.split('/')[0] || 'U').charAt(0).toUpperCase()}</div>`
    }));
}

async function fetchLeaderboard() {
    const ratingsResponse = await fetch('/api/ratings');
    const ratings = await ratingsResponse.json();
    
    state.leaderboardData = Object.entries(ratings)
        .map(([id, data]) => {
            const llm = state.llms.find(l => l.id === id) || { 
                id, 
                name: id.split('/')[1] || id, 
                provider: id.split('/')[0] || 'Unknown',
                avatar: `<div class="w-full h-full bg-gray-600 rounded-full flex items-center justify-center text-white font-bold text-lg">${(id.split('/')[0] || 'U').charAt(0).toUpperCase()}</div>`
            };
            
            const wins = data.wins;
            const draws = data.draws;
            const losses = data.losses;
            const total = wins + draws + losses;
            const winRate = total > 0 ? Math.round((wins / total) * 100) : 0;
            
            const moves = data.moves || 0;
            const time = data.time || 0.0;
            const cost = data.cost || 0.0;
            const avgTimePerMove = moves > 0 ? time / moves : 0;
            const avgCostPerMove = moves > 0 ? cost / moves : 0;
            
            return {
                ...llm,
                elo: Math.round(data.rating),
                matchesPlayed: total,
                winRate: winRate,
                wins: wins,
                draws: draws,
                losses: losses,
                moves: moves,
                time: time,
                cost: cost,
                avgTimePerMove: avgTimePerMove,
                avgCostPerMove: avgCostPerMove
            };
        })
        .sort((a, b) => b.elo - a.elo);
}


// --- INIT ---
document.addEventListener('DOMContentLoaded', async () => {
    state.theme = 'light';

    await fetchModels();
    await fetchLeaderboard();

    // Now that we have data, we can update ELOs in the llms list
    state.llms.forEach(llm => {
        const ratingEntry = state.leaderboardData.find(entry => entry.id === llm.id);
        if (ratingEntry) {
            llm.elo = ratingEntry.elo;
        }
    });

    render();
});
