import { Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom';
import Hero from './components/Hero';
import QuizPage from './components/QuizPage';
import ResultsSection from './components/ResultsSection';
import UploadSection from './components/UploadSection';

function UploadPage() {
    const navigate = useNavigate();

    const handleUploadStart = (newJobId) => {
        navigate(`/jobs/${newJobId}`);
    };

    return <UploadSection onUploadStart={handleUploadStart} />;
}

function JobPage() {
    const navigate = useNavigate();
    const { jobId } = useParams();

    if (!jobId) {
        return <Navigate to="/" replace />;
    }

    const handleReset = () => {
        navigate('/');
    };

    return <ResultsSection jobId={jobId} onReset={handleReset} />;
}

export default function App() {

    return (
        <div style={{ backgroundColor: 'var(--paper)', minHeight: '100vh' }}>
            <Hero />

            <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                <Routes>
                    <Route path="/" element={<UploadPage />} />
                    <Route path="/jobs/:jobId" element={<JobPage />} />
                    <Route path="/quiz" element={<QuizPage />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </div>
        </div>
    );
}
