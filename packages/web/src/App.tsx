import { useState } from 'react';
import { SubmitForm } from './components/SubmitForm';
import { JobList } from './components/JobList';
import { TranscriptView } from './components/TranscriptView';

function App() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }}>
      {selectedJobId ? (
        <TranscriptView
          jobId={selectedJobId}
          onClose={() => setSelectedJobId(null)}
        />
      ) : (
        <div className="max-w-6xl mx-auto px-6 py-10 animate-fade-in">
          <header className="mb-10">
            <h1 className="text-3xl font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              Transcripts
            </h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>
              YouTube and X video transcription
            </p>
          </header>

          <SubmitForm />
          <JobList onSelectJob={setSelectedJobId} />
        </div>
      )}
    </div>
  );
}

export default App;
