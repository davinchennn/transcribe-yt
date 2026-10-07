import { useState } from 'react';
import { SubmitForm } from './components/SubmitForm';
import { JobList } from './components/JobList';
import { TranscriptView } from './components/TranscriptView';

function App() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  return (
    <div className="app-shell">
      <header className="app-masthead">
        <button className="app-wordmark" onClick={() => setSelectedJobId(null)} aria-label="Transcripts home">Transcripts</button>
        <span className="masthead-note">YouTube + X</span>
      </header>
      {selectedJobId ? (
        <TranscriptView
          jobId={selectedJobId}
          onClose={() => setSelectedJobId(null)}
        />
      ) : (
        <main className="library-page animate-fade-in">
          <header className="library-intro">
            <div>
              <h1>Conversations, in perspective.</h1>
            </div>
            <div className="library-intro-note">
              <p>Read, search, and explore your videos.</p>
            </div>
          </header>

          <SubmitForm />
          <JobList onSelectJob={setSelectedJobId} />
        </main>
      )}
    </div>
  );
}

export default App;
