const fs = require('fs');

let app = fs.readFileSync('src/App.tsx', 'utf8');

// The replacement logic:

// 1. We define a fetchWrapper that injects the auth token
const helper = `
const getToken = () => localStorage.getItem('bot_token') || '';
const setToken = (t) => {
    if (t) localStorage.setItem('bot_token', t.trim());
    else localStorage.removeItem('bot_token');
    window.location.reload();
};

const apiFetch = async (url, options = {}) => {
    const headers = { ...options.headers, 'x-auth-token': getToken() };
    return fetch(url, { ...options, headers });
};
`;
app = app.replace("const WORKER_URL = 'https://dubbing-chearb-worker.yokthanwa1993-bc9.workers.dev'", helper + "\nconst WORKER_URL = 'https://dubbing-chearb-worker.yokthanwa1993-bc9.workers.dev'");

app = app.replace(/fetch\(\`\$\{WORKER_URL\}/g, "apiFetch(`${WORKER_URL}");

// Inside function App()
const authState = `
  const [token, setTokenState] = useState(() => {
    try { return localStorage.getItem('bot_token') || '' } catch { return '' }
  });
  const [loginInput, setLoginInput] = useState('');

  if (!token) {
    return (
      <div className="h-screen bg-white flex flex-col items-center justify-center p-6 text-center font-['Sukhumvit_Set','Kanit',sans-serif]">
        <div className="w-20 h-20 bg-blue-50 text-blue-500 rounded-3xl flex items-center justify-center mb-6 shadow-sm">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        </div>
        <h1 className="text-2xl font-extrabold text-gray-900 mb-2">Login Bot Workspace</h1>
        <p className="text-sm text-gray-500 mb-8 max-w-[280px]">กรุณาใส่ Telegram Bot Token ประจำพื้นที่ทำงานของคุณ</p>
        
        <div className="w-full max-w-sm">
          <input 
            type="text" 
            value={loginInput}
            onChange={(e) => setLoginInput(e.target.value)}
            placeholder="e.g. 123456789:AAH..."
            className="w-full bg-gray-50 border border-gray-200 rounded-2xl px-5 py-4 text-sm font-mono outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition-all text-center mb-4"
          />
          <button 
            onClick={() => {
                if (loginInput.trim()) setToken(loginInput.trim());
            }}
            disabled={!loginInput.trim()}
            className="w-full bg-blue-600 text-white font-bold py-4 rounded-2xl active:scale-95 transition-all disabled:bg-gray-300 shadow-md shadow-blue-200"
          >
            ต่อไป
          </button>
        </div>
      </div>
    );
  }
`;

app = app.replace("function App() {\n", "function App() {\n" + authState);

const logoutBtn = `
            {/* Logout Bot */}
            <div className="pt-2">
              <button 
                 onClick={() => setToken('')}
                 className="w-full bg-red-50 text-red-600 border border-red-100 py-4 rounded-2xl font-bold flex flex-col items-center justify-center gap-1 active:scale-95 transition-transform"
              >
                  <span>Switch Bot</span>
                  <span className="text-[10px] text-red-400 font-mono font-normal">Token: {token.slice(0,10)}...</span>
              </button>
            </div>
`;
app = app.replace('<p className="text-gray-300 text-xs font-medium">Version 2.0.1 (Build 240)</p>', logoutBtn + '\n<p className="text-gray-300 text-xs font-medium">Version 2.0.1 (Build 240)</p>');

fs.writeFileSync('src/App.tsx', app);
