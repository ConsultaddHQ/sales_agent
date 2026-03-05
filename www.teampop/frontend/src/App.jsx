import AvatarWidget from './components/AvatarWidget';
import './App.css';

// ElevenLabs Agent ID — replace with your actual agent ID or pass via
// window.__TEAM_POP_AGENT_ID__ from the embed snippet.
const AGENT_ID = window.__TEAM_POP_AGENT_ID__ || 'agent_9701kjray80jft7sv8trbqfqsaj1';

function App() {
  return (
    <div className="app-container">
      <AvatarWidget agentId={AGENT_ID} />
    </div>
  );
}

export default App;
