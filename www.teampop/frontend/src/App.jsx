import AvatarWidget from './components/AvatarWidget';
import './App.css';

// ElevenLabs Agent ID — replace with your actual agent ID or pass via
// window.__TEAM_POP_AGENT_ID__ from the embed snippet.
const AGENT_ID = window.__TEAM_POP_AGENT_ID__ || 'agent_5701kjfw2tqjemzscap6316jac9y';

function App() {
  return (
    <div className="app-container">
      <AvatarWidget agentId={AGENT_ID} />
    </div>
  );
}

export default App;
