import { useState } from 'react';
import Hero from './components/Hero';
import ResultsSection from './components/ResultsSection';
import UploadSection from './components/UploadSection';

export default function App() {
    const [jobId, setJobId] = useState(null);
    const [status, setStatus] = useState('idle');
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);

    const handleUploadStart = (newJobId) => {
        setJobId(newJobId);
        setStatus('processing');
        setResults(null);
        setError(null);
    };

    const handleComplete = (jobResults) => {
        setResults(jobResults);
        setStatus('complete');
    };

    const handleError = (errorMsg) => {
        setError(errorMsg);
        setStatus('error');
    };

    const handleReset = () => {
        setJobId(null);
        setStatus('idle');
        setResults(null);
        setError(null);
    };

    return (
        <div style={{ backgroundColor: 'var(--paper)', minHeight: '100vh' }}>
            <Hero />

            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                {status === 'idle' && (
                    <UploadSection onUploadStart={handleUploadStart} />
                )}

                {status !== 'idle' && (
                    <ResultsSection
                        jobId={jobId}
                        status={status}
                        results={results}
                        error={error}
                        onComplete={handleComplete}
                        onError={handleError}
                        onReset={handleReset}
                    />
                )}
            </div>
        </div>
    );
}
