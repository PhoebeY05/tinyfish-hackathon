import { useEffect, useState } from 'react';
import ImageCard from './ImageCard';
import ProgressBar from './ProgressBar';

function getJobStorageKey(jobId) {
    return `tinyfish:job:${jobId}`;
}

function readCachedJobState(jobId) {
    if (!jobId || typeof window === 'undefined') {
        return null;
    }

    try {
        const raw = window.localStorage.getItem(getJobStorageKey(jobId));
        if (!raw) {
            return null;
        }
        return JSON.parse(raw);
    } catch (err) {
        console.warn('Failed to parse cached job state', err);
        return null;
    }
}

function writeCachedJobState(jobId, state) {
    if (!jobId || typeof window === 'undefined') {
        return;
    }

    try {
        window.localStorage.setItem(getJobStorageKey(jobId), JSON.stringify(state));
    } catch (err) {
        console.warn('Failed to cache job state', err);
    }
}

function clearCachedJobState(jobId) {
    if (!jobId || typeof window === 'undefined') {
        return;
    }

    try {
        window.localStorage.removeItem(getJobStorageKey(jobId));
    } catch (err) {
        console.warn('Failed to clear cached job state', err);
    }
}

export default function ResultsSection({ jobId, onReset }) {
    const [job, setJob] = useState(null);
    const [status, setStatus] = useState('processing');
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const [pollError, setPollError] = useState(null);

    useEffect(() => {
        const cached = readCachedJobState(jobId);
        if (!cached) {
            setJob(null);
            setStatus('processing');
            setResults(null);
            setError(null);
            setPollError(null);
            return;
        }

        setJob(cached.job ?? null);
        setStatus(cached.status ?? 'processing');
        setResults(cached.results ?? null);
        setError(cached.error ?? null);
        setPollError(cached.pollError ?? null);
    }, [jobId]);

    useEffect(() => {
        writeCachedJobState(jobId, {
            job,
            status,
            results,
            error,
            pollError,
            updatedAt: new Date().toISOString(),
        });
    }, [jobId, job, status, results, error, pollError]);

    useEffect(() => {
        if (!jobId || status === 'error') return;
        if (status === 'complete' && job?.progress?.evidence_completed) return;

        const pollInterval = setInterval(async () => {
            try {
                const res = await fetch(`/jobs/${jobId}`);
                if (!res.ok) throw new Error(`Failed to fetch job: ${res.status}`);

                const jobData = await res.json();
                setJob(jobData);

                if (jobData.status === 'completed') {
                    const resultsRes = await fetch(`/jobs/${jobId}/results`);
                    if (!resultsRes.ok) throw new Error('Failed to fetch results');
                    const resultsData = await resultsRes.json();
                    setResults(resultsData);
                    setStatus('complete');
                    if (jobData.progress?.evidence_completed) {
                        clearInterval(pollInterval);
                    }
                } else if (jobData.status === 'failed') {
                    setError(jobData.error || 'Job failed');
                    setStatus('error');
                    clearInterval(pollInterval);
                }
            } catch (err) {
                setPollError(err.message);
                console.error('Poll error:', err);
            }
        }, 1200);

        return () => clearInterval(pollInterval);
    }, [jobId, status, job?.progress?.evidence_completed]);

    const handleResetClick = () => {
        clearCachedJobState(jobId);
        onReset();
    };

    if (error) {
        return (
            <div
                className="p-6 sm:p-8 border"
                style={{
                    borderColor: 'var(--border)',
                    borderWidth: '1px',
                    backgroundColor: 'var(--card)',
                }}
            >
                <h2 className="font-serif text-2xl font-bold mb-4" style={{ color: 'var(--ink)' }}>
                    Error
                </h2>
                <div
                    className="p-4 border mb-4"
                    style={{
                        borderColor: 'var(--danger)',
                        borderWidth: '1px',
                        backgroundColor: '#fffaf7',
                    }}
                >
                    <p className="text-sm font-mono" style={{ color: 'var(--danger)' }}>
                        {error}
                    </p>
                </div>
                {pollError && (
                    <div
                        className="p-4 border mb-6"
                        style={{
                            borderColor: 'var(--accent2)',
                            borderWidth: '1px',
                            backgroundColor: '#fefdf4',
                        }}
                    >
                        <p className="text-xs font-mono" style={{ color: 'var(--accent2)' }}>
                            {pollError}
                        </p>
                    </div>
                )}
                <button
                    onClick={handleResetClick}
                    className="btn-primary"
                >
                    Start Over
                </button>
            </div>
        );
    }

    if (status === 'processing' && job) {
        return (
            <div className="space-y-6">
                <div
                    className="p-6 sm:p-8 border"
                    style={{
                        borderColor: 'var(--border)',
                        borderWidth: '1px',
                        backgroundColor: 'var(--card)',
                    }}
                >
                    <h2 className="font-serif text-2xl font-bold mb-6" style={{ color: 'var(--ink)' }}>
                        Analyzing With OpenAI + TinyFish
                    </h2>
                    <ProgressBar job={job} />
                </div>
            </div>
        );
    }

    if (status === 'complete' && results) {
        const totalImages = results.images?.length || 0;
        const identifiedCount = results.images?.filter((img) => img.predictions?.length > 0).length || 0;
        const disputesCount = results.images?.filter((img) => img.dispute?.status && img.dispute.status !== 'no_dispute').length || 0;
        const avgConfidence = results.images?.length
            ? Math.round((results.images.reduce((sum, img) => sum + (img.predictions?.[0]?.confidence || 0), 0) / results.images.length) * 100)
            : 0;
        const evidenceInBackground = Boolean(job?.progress?.evidence_background_running);
        const evidenceDone = Boolean(job?.progress?.evidence_completed);
        const evidenceNotification = job?.progress?.notification;
        const processedSpeciesGroups = Number(job?.progress?.processed_species_groups || 0);
        const totalSpeciesGroups = Number(job?.progress?.total_species_groups || 0);
        const tinyfishLogs = Array.isArray(job?.progress?.logs)
            ? job.progress.logs.filter((line) => typeof line === 'string' && line.includes('TinyFish')).slice(-80)
            : [];

        const speciesLogMap = {};
        let activeSpeciesKey = null;
        tinyfishLogs.forEach((line) => {
            const groupMatch = line.match(/\(([^,]+),\s*\d+\s*images\)/i);
            if (groupMatch?.[1]) {
                activeSpeciesKey = groupMatch[1].trim().toLowerCase();
                if (!speciesLogMap[activeSpeciesKey]) {
                    speciesLogMap[activeSpeciesKey] = [];
                }
                speciesLogMap[activeSpeciesKey].push(line);
                return;
            }

            if (activeSpeciesKey) {
                if (!speciesLogMap[activeSpeciesKey]) {
                    speciesLogMap[activeSpeciesKey] = [];
                }
                speciesLogMap[activeSpeciesKey].push(line);
            }
        });

        return (
            <div className="space-y-6">
                {evidenceInBackground || evidenceDone ? (
                    <div
                        className="p-4 border"
                        style={{
                            borderColor: evidenceDone ? 'var(--accent2)' : 'var(--border)',
                            borderWidth: '1px',
                            backgroundColor: evidenceDone ? '#f7fbf8' : '#fafaf8',
                        }}
                    >
                        <p className="text-sm font-mono" style={{ color: 'var(--ink)' }}>
                            {evidenceNotification || (evidenceDone ? 'Evidence search completed.' : 'TinyFish evidence search is still running in background...')}
                        </p>
                        {totalSpeciesGroups > 0 ? (
                            <p className="text-xs font-mono mt-2" style={{ color: 'var(--muted)' }}>
                                Evidence groups processed: {processedSpeciesGroups} / {totalSpeciesGroups}
                            </p>
                        ) : null}
                    </div>
                ) : null}

                {/* Summary Bar */}
                <div
                    className="grid grid-cols-2 sm:grid-cols-4 gap-4 p-6 sm:p-8 border"
                    style={{
                        borderColor: 'var(--border)',
                        borderWidth: '1px',
                        backgroundColor: 'var(--card)',
                    }}
                >
                    <div className="text-center">
                        <div className="text-3xl font-bold font-serif" style={{ color: 'var(--accent)' }}>
                            {totalImages}
                        </div>
                        <div className="text-xs tracking-widest uppercase text-muted mt-1 font-mono">Photos</div>
                    </div>
                    <div className="text-center">
                        <div className="text-3xl font-bold font-serif" style={{ color: 'var(--accent)' }}>
                            {identifiedCount}
                        </div>
                        <div className="text-xs tracking-widest uppercase text-muted mt-1 font-mono">Identified</div>
                    </div>
                    <div className="text-center">
                        <div className="text-3xl font-bold font-serif" style={{ color: 'var(--accent2)' }}>
                            {disputesCount}
                        </div>
                        <div className="text-xs tracking-widest uppercase text-muted mt-1 font-mono">Disputes</div>
                    </div>
                    <div className="text-center">
                        <div className="text-3xl font-bold font-serif" style={{ color: 'var(--accent)' }}>
                            {avgConfidence}%
                        </div>
                        <div className="text-xs tracking-widest uppercase text-muted mt-1 font-mono">Avg Conf</div>
                    </div>
                </div>

                {/* Results Header */}
                <div
                    className="p-6 sm:p-8 border flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4"
                    style={{
                        borderColor: 'var(--border)',
                        borderWidth: '1px',
                        backgroundColor: 'var(--card)',
                    }}
                >
                    <h2 className="font-serif text-2xl font-bold" style={{ color: 'var(--ink)' }}>
                        Bird Reports
                    </h2>
                    <a
                        href={`/jobs/${jobId}/download`}
                        className="btn-primary text-center"
                    >
                        Download Report ZIP
                    </a>
                </div>

                {/* Image Cards Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {results.images?.map((image) => {
                        const speciesKey = (image.primary_prediction?.common_name || '').trim().toLowerCase();
                        const scopedLogs = speciesLogMap[speciesKey] || [];
                        return (
                            <ImageCard key={image.image_id} image={image} tinyfishLogs={scopedLogs} jobId={jobId} />
                        );
                    })}
                </div>

                {/* Reset Button */}
                <button
                    onClick={handleResetClick}
                    className="w-full px-6 py-3 font-mono text-sm border"
                    style={{
                        borderColor: 'var(--border)',
                        borderWidth: '1px',
                        color: 'var(--ink)',
                        backgroundColor: 'var(--card)',
                    }}
                >
                    Analyze Another Batch
                </button>
            </div>
        );
    }

    return null;
}
