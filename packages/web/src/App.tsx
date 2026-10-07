import { SubmitForm } from './components/SubmitForm';
import { JobList } from './components/JobList';
import { TranscriptView } from './components/TranscriptView';
import { RouteLink } from './components/RouteLink';
import { useRoute } from './hooks/useRoute';
import { navigate, transcriptPath } from './lib/routing';

function App() {
  const route = useRoute();

  return (
    <div className="app-shell">
      <header className="app-masthead">
        <RouteLink className="app-wordmark" href="/" aria-label="Transcripts home">Transcripts</RouteLink>
        <span className="masthead-note">YouTube + X</span>
      </header>
      {route.page === 'transcript' ? (
        <TranscriptView
          key={route.jobId}
          jobId={route.jobId}
          view={route.view}
          onViewChange={(view) => navigate(transcriptPath(route.jobId, view))}
        />
      ) : route.page === 'home' ? (
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
          <JobList />
        </main>
      ) : (
        <main className="library-page animate-fade-in">
          <header className="library-intro"><h1>Page not found.</h1></header>
          <RouteLink className="nav-link" href="/">Return to the archive</RouteLink>
        </main>
      )}
    </div>
  );
}

export default App;
