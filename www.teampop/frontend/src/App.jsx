import { Component } from 'react';
import { ConversationProvider } from '@elevenlabs/react';
import AvatarWidget from './components/AvatarWidget';
import { reportError, setTelemetryContext } from './telemetry';
const AGENT_ID = window.__TEAM_POP_AGENT_ID__ || 'agent_3501kk2fst2nfff9zr7teg3m2mf1';

setTelemetryContext({ agentId: AGENT_ID });

// A widget render crash must never take down the merchant's page, and must
// never be silent — report it and render nothing.
class WidgetErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { crashed: false };
  }
  static getDerivedStateFromError() {
    return { crashed: true };
  }
  componentDidCatch(error, info) {
    console.error('[TeamPop] widget crashed:', error);
    reportError(error, { where: 'render', componentStack: info?.componentStack });
  }
  render() {
    return this.state.crashed ? null : this.props.children;
  }
}

function App() {
  return (
    <WidgetErrorBoundary>
      <ConversationProvider>
        <div className="app-container">
          <AvatarWidget agentId={AGENT_ID} />
        </div>
      </ConversationProvider>
    </WidgetErrorBoundary>
  );
}

export default App;
