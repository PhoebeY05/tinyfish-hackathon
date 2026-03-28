import { useState } from 'react';

export default function UploadSection({ onUploadStart }) {
    const [file, setFile] = useState(null);
    const [geography, setGeography] = useState('Singapore');
    const [loading, setLoading] = useState(false);
    const [localError, setLocalError] = useState(null);
    const [dragOver, setDragOver] = useState(false);

    const handleDragOver = (e) => {
        e.preventDefault();
        setDragOver(true);
    };

    const handleDragLeave = () => {
        setDragOver(false);
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer.files[0]) {
            validateAndSetFile(e.dataTransfer.files[0]);
        }
    };

    const validateAndSetFile = (selectedFile) => {
        if (!selectedFile.name.toLowerCase().endsWith('.zip')) {
            setLocalError('Only .zip files are supported.');
            setFile(null);
        } else {
            setFile(selectedFile);
            setLocalError(null);
        }
    };

    const handleFileChange = (e) => {
        const selected = e.target.files?.[0];
        if (selected) {
            validateAndSetFile(selected);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!file) {
            setLocalError('Please select a .zip file.');
            return;
        }

        setLoading(true);
        setLocalError(null);

        try {
            const formData = new FormData();
            formData.append('photosZip', file);
            formData.append('geography', geography);

            const res = await fetch('/uploads', { method: 'POST', body: formData });
            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.detail || `Upload failed: ${res.status}`);
            }

            const data = await res.json();
            onUploadStart(data.jobId);
        } catch (err) {
            setLocalError(err.message);
            setLoading(false);
        }
    };

    const geographies = ['Singapore', 'Malaysia', 'Indonesia', 'Thailand', 'Brunei'];

    return (
        <div className="max-w-4xl mx-auto px-8 py-12">
            <div
                className="border-2 border-dashed p-12 sm:p-16 text-center cursor-pointer transition-colors"
                style={{
                    borderColor: dragOver ? 'var(--accent)' : 'var(--border)',
                    backgroundColor: dragOver ? '#f9fdf7' : 'var(--card)',
                }}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
            >
                <span className="text-5xl sm:text-6xl mb-6 block">🦅</span>
                <h2 className="font-serif text-2xl sm:text-3xl font-bold mb-2" style={{ color: 'var(--ink)' }}>
                    Drop your ZIP of bird photos
                </h2>
                <p className="text-xs sm:text-sm tracking-widest uppercase text-muted mb-8 font-mono">
                    Supports .zip containing .jpg, .jpeg, .png, .webp images
                </p>

                <button
                    type="button"
                    onClick={() => document.getElementById('fileInput').click()}
                    className="btn-primary"
                    disabled={loading}
                >
                    Select ZIP File
                </button>

                <input
                    id="fileInput"
                    type="file"
                    accept=".zip"
                    onChange={handleFileChange}
                    className="hidden"
                />

                {file && (
                    <p className="mt-4 text-xs font-mono" style={{ color: 'var(--accent)' }}>
                        ✓ {file.name}
                    </p>
                )}

                {localError && (
                    <div className="mt-4 text-xs font-mono" style={{ color: 'var(--danger)' }}>
                        ❌ {localError}
                    </div>
                )}
            </div>

            {file && !loading && (
                <div className="mt-8 flex flex-col sm:flex-row gap-3 sm:gap-4 items-center justify-center">
                    <select
                        value={geography}
                        onChange={(e) => setGeography(e.target.value)}
                        className="px-4 py-2 font-mono text-xs border"
                        style={{
                            borderColor: 'var(--border)',
                            borderWidth: '1px',
                            backgroundColor: 'var(--card)',
                            color: 'var(--ink)',
                        }}
                    >
                        {geographies.map((geo) => (
                            <option key={geo} value={geo}>
                                {geo}
                            </option>
                        ))}
                    </select>

                    <button onClick={handleSubmit} disabled={loading} className="btn-primary">
                        {loading ? 'Uploading...' : 'Analyze All Birds'}
                    </button>
                </div>
            )}
        </div>
    );
}
