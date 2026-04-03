import { ConversationProvider } from '@elevenlabs/react';
import AvatarWidget from './components/AvatarWidget';
import './App.css';

// ElevenLabs Agent ID — replace with your actual agent ID or pass via
// window.__TEAM_POP_AGENT_ID__ from the embed snippet.
const AGENT_ID = window.__TEAM_POP_AGENT_ID__ || 'agent_3501kk2fst2nfff9zr7teg3m2mf1';

function App() {
  return (
    <ConversationProvider>
      <div className="app-container">
        <AvatarWidget agentId={AGENT_ID} />
      </div>
    </ConversationProvider>
  );
}

export default App;
