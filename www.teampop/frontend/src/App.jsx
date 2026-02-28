import AvatarWidget from './components/AvatarWidget';
import './App.css';

// ElevenLabs Agent ID — replace with your actual agent ID or pass via
// window.__TEAM_POP_AGENT_ID__ from the embed snippet.
const AGENT_ID = window.__TEAM_POP_AGENT_ID__ || 'agent_3201kjj5r1bqexrb3rzgafq0s5nn';

function App() {
  return (
    <div className="app-container">
      <AvatarWidget agentId={AGENT_ID} />
    </div>
  );
}

export default App;
