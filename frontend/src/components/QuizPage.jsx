import { useEffect, useMemo, useState } from 'react';

const QUIZ_LOCAL_FALLBACK = [
    { commonName: 'Asian Koel', wikipediaTitle: 'Asian_koel', aliases: ['asian koel', 'koel'] },
    {
        commonName: 'Collared Kingfisher',
        wikipediaTitle: 'Collared_kingfisher',
        aliases: ['collared kingfisher', 'white-collared kingfisher', 'kingfisher'],
    },
    {
        commonName: 'Olive-backed Sunbird',
        wikipediaTitle: 'Olive-backed_sunbird',
        aliases: ['olive-backed sunbird', 'olive backed sunbird', 'yellow-bellied sunbird', 'sunbird'],
    },
    {
        commonName: 'Yellow-vented Bulbul',
        wikipediaTitle: 'Yellow-vented_bulbul',
        aliases: ['yellow-vented bulbul', 'yellow vented bulbul', 'bulbul'],
    },
    {
        commonName: 'Brahminy Kite',
        wikipediaTitle: 'Brahminy_kite',
        aliases: ['brahminy kite', 'red-backed sea eagle', 'red backed sea eagle', 'kite'],
    },
    {
        commonName: 'Black-naped Oriole',
        wikipediaTitle: 'Black-naped_oriole',
        aliases: ['black-naped oriole', 'black naped oriole', 'oriole'],
    },
    {
        commonName: 'Javan Myna',
        wikipediaTitle: 'Javan_myna',
        aliases: ['javan myna', 'white-vented myna', 'white vented myna', 'myna'],
    },
    {
        commonName: 'White-throated Kingfisher',
        wikipediaTitle: 'White-throated_kingfisher',
        aliases: ['white-throated kingfisher', 'white throated kingfisher', 'kingfisher'],
    },
    {
        commonName: 'Scarlet-backed Flowerpecker',
        wikipediaTitle: 'Scarlet-backed_flowerpecker',
        aliases: ['scarlet-backed flowerpecker', 'scarlet backed flowerpecker', 'flowerpecker'],
    },
    {
        commonName: 'Eurasian Tree Sparrow',
        wikipediaTitle: 'Eurasian_tree_sparrow',
        aliases: ['eurasian tree sparrow', 'tree sparrow', 'sparrow'],
    },
];

const HIGH_SCORE_KEY = 'tinyfish:quiz:high-score';
const LAST_SCORE_KEY = 'tinyfish:quiz:last-score';

function normalizeText(text) {
    return String(text || '')
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function isCorrectAnswer(guess, aliases) {
    const normalizedGuess = normalizeText(guess);
    if (!normalizedGuess) return false;

    return aliases.some((alias) => {
        const normalizedAlias = normalizeText(alias);
        return normalizedGuess === normalizedAlias || normalizedGuess.includes(normalizedAlias);
    });
}

function shuffle(items) {
    const copy = [...items];
    for (let i = copy.length - 1; i > 0; i -= 1) {
        const j = Math.floor(Math.random() * (i + 1));
        [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
}

async function fetchWikipediaImage(species) {
    const wikipediaTitle = species.wikipediaTitle || species.commonName.replace(/\s+/g, '_');
    const endpoint = `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(wikipediaTitle)}`;

    try {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`Wikipedia summary failed: ${response.status}`);
        }

        const data = await response.json();
        return {
            ...species,
            imageUrl: data.originalimage?.source || data.thumbnail?.source || null,
            sourceUrl: data.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${wikipediaTitle}`,
            sourceName: 'Wikipedia',
        };
    } catch (err) {
        console.warn(`Failed to fetch image for ${species.commonName}`, err);
        return {
            ...species,
            imageUrl: null,
            sourceUrl: `https://en.wikipedia.org/wiki/${wikipediaTitle}`,
            sourceName: 'Wikipedia',
        };
    }
}

export default function QuizPage() {
    const [phase, setPhase] = useState('setup');
    const [questionCount, setQuestionCount] = useState(5);
    const [timedMode, setTimedMode] = useState(false);
    const [secondsPerQuestion, setSecondsPerQuestion] = useState(20);

    const [questions, setQuestions] = useState([]);
    const [speciesPool, setSpeciesPool] = useState(QUIZ_LOCAL_FALLBACK);
    const [geography, setGeography] = useState('Global');
    const [catalogSource, setCatalogSource] = useState('local');
    const [catalogError, setCatalogError] = useState(null);
    const [loadingQuestions, setLoadingQuestions] = useState(false);
    const [questionIndex, setQuestionIndex] = useState(0);
    const [guess, setGuess] = useState('');
    const [score, setScore] = useState(0);
    const [answered, setAnswered] = useState(false);
    const [lastCorrect, setLastCorrect] = useState(false);
    const [timeLeft, setTimeLeft] = useState(20);

    const [highScore, setHighScore] = useState(() => {
        if (typeof window === 'undefined') return 0;
        return Number(window.localStorage.getItem(HIGH_SCORE_KEY) || 0);
    });

    const [lastScore, setLastScore] = useState(() => {
        if (typeof window === 'undefined') return null;
        const raw = window.localStorage.getItem(LAST_SCORE_KEY);
        return raw ? JSON.parse(raw) : null;
    });

    const currentQuestion = questions[questionIndex] || null;

    const accuracy = useMemo(() => {
        if (!questions.length) return 0;
        return Math.round((score / questions.length) * 100);
    }, [score, questions.length]);

    const loadSpeciesCatalog = async (geo) => {
        try {
            const res = await fetch(`/api/quiz/species?geography=${encodeURIComponent(geo)}&limit=300`);
            if (!res.ok) {
                throw new Error(`Catalog fetch failed: ${res.status}`);
            }

            const data = await res.json();
            const remoteSpecies = Array.isArray(data.species) && data.species.length > 0 ? data.species : QUIZ_LOCAL_FALLBACK;
            setSpeciesPool(remoteSpecies);
            setCatalogSource(data.source || 'tinyfish');
            setCatalogError(data.error || null);
            return remoteSpecies;
        } catch (err) {
            setSpeciesPool(QUIZ_LOCAL_FALLBACK);
            setCatalogSource('local');
            setCatalogError(err.message);
            return QUIZ_LOCAL_FALLBACK;
        }
    };

    useEffect(() => {
        loadSpeciesCatalog(geography);
    }, [geography]);

    useEffect(() => {
        if (!timedMode || phase !== 'playing' || answered) return undefined;

        const tick = window.setInterval(() => {
            setTimeLeft((prev) => {
                if (prev <= 1) {
                    window.clearInterval(tick);
                    setAnswered(true);
                    setLastCorrect(false);
                    return 0;
                }
                return prev - 1;
            });
        }, 1000);

        return () => window.clearInterval(tick);
    }, [timedMode, phase, answered, questionIndex]);

    useEffect(() => {
        if (phase !== 'finished') return;

        if (score > highScore) {
            setHighScore(score);
            window.localStorage.setItem(HIGH_SCORE_KEY, String(score));
        }

        const latest = {
            score,
            total: questions.length,
            accuracy: questions.length ? Math.round((score / questions.length) * 100) : 0,
            timedMode,
            completedAt: new Date().toISOString(),
        };
        setLastScore(latest);
        window.localStorage.setItem(LAST_SCORE_KEY, JSON.stringify(latest));
    }, [phase, score, questions.length, highScore, timedMode]);

    const startQuiz = async () => {
        setLoadingQuestions(true);
        setPhase('setup');

        const catalog = speciesPool.length > 0 ? speciesPool : await loadSpeciesCatalog(geography);
        const selected = shuffle(catalog).slice(0, Math.min(questionCount, catalog.length));
        const withImages = await Promise.all(selected.map(fetchWikipediaImage));

        setQuestions(withImages);
        setQuestionIndex(0);
        setGuess('');
        setScore(0);
        setAnswered(false);
        setLastCorrect(false);
        setTimeLeft(secondsPerQuestion);
        setPhase('playing');
        setLoadingQuestions(false);
    };

    const submitAnswer = () => {
        if (!currentQuestion || answered) return;

        const aliases = Array.isArray(currentQuestion.aliases) ? currentQuestion.aliases : [];
        const correct = isCorrectAnswer(guess, [currentQuestion.commonName, ...aliases]);
        setLastCorrect(correct);
        setAnswered(true);

        if (correct) {
            setScore((prev) => prev + 1);
        }
    };

    const nextQuestion = () => {
        const nextIndex = questionIndex + 1;
        if (nextIndex >= questions.length) {
            setPhase('finished');
            return;
        }

        setQuestionIndex(nextIndex);
        setGuess('');
        setAnswered(false);
        setLastCorrect(false);
        setTimeLeft(secondsPerQuestion);
    };

    const restartQuiz = () => {
        setPhase('setup');
        setQuestions([]);
        setQuestionIndex(0);
        setGuess('');
        setScore(0);
        setAnswered(false);
        setLastCorrect(false);
        setTimeLeft(secondsPerQuestion);
    };

    if (phase === 'setup') {
        return (
            <div
                className="p-6 sm:p-8 border max-w-3xl mx-auto"
                style={{ borderColor: 'var(--border)', borderWidth: '1px', backgroundColor: 'var(--card)' }}
            >
                <h2 className="font-serif text-3xl font-bold mb-3" style={{ color: 'var(--ink)' }}>
                    Bird Quiz Lab
                </h2>
                <p className="text-sm font-mono text-muted mb-8">
                    Identify birds from photos, track your score, and chase your personal best.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mb-6">
                    <label className="block">
                        <span className="text-xs font-mono tracking-widest uppercase text-muted">Region</span>
                        <select
                            value={geography}
                            onChange={(e) => setGeography(e.target.value)}
                            className="mt-2 w-full px-4 py-2 border bg-card font-mono text-sm"
                            style={{ borderColor: 'var(--border)' }}
                        >
                            <option value="Global">Global</option>
                            <option value="Singapore">Singapore</option>
                            <option value="Malaysia">Malaysia</option>
                            <option value="Indonesia">Indonesia</option>
                            <option value="Thailand">Thailand</option>
                            <option value="Brunei">Brunei</option>
                        </select>
                    </label>

                    <label className="block">
                        <span className="text-xs font-mono tracking-widest uppercase text-muted">Questions</span>
                        <select
                            value={questionCount}
                            onChange={(e) => setQuestionCount(Number(e.target.value))}
                            className="mt-2 w-full px-4 py-2 border bg-card font-mono text-sm"
                            style={{ borderColor: 'var(--border)' }}
                        >
                            <option value={5}>5 Questions</option>
                            <option value={8}>8 Questions</option>
                            <option value={10}>10 Questions</option>
                        </select>
                    </label>

                    <label className="block">
                        <span className="text-xs font-mono tracking-widest uppercase text-muted">Mode</span>
                        <select
                            value={timedMode ? 'timed' : 'untimed'}
                            onChange={(e) => setTimedMode(e.target.value === 'timed')}
                            className="mt-2 w-full px-4 py-2 border bg-card font-mono text-sm"
                            style={{ borderColor: 'var(--border)' }}
                        >
                            <option value="untimed">Practice (Untimed)</option>
                            <option value="timed">Timed Challenge</option>
                        </select>
                    </label>
                </div>

                <div className="text-xs font-mono text-muted mb-6">
                    Species pool: {speciesPool.length} birds · Source: {catalogSource}
                    {catalogError ? ` · Fallback reason: ${catalogError}` : ''}
                </div>

                {timedMode && (
                    <label className="block mb-8">
                        <span className="text-xs font-mono tracking-widest uppercase text-muted">Seconds Per Question</span>
                        <input
                            type="range"
                            min={8}
                            max={30}
                            step={1}
                            value={secondsPerQuestion}
                            onChange={(e) => setSecondsPerQuestion(Number(e.target.value))}
                            className="mt-3 w-full"
                        />
                        <div className="text-sm font-mono mt-2" style={{ color: 'var(--ink)' }}>
                            {secondsPerQuestion}s
                        </div>
                    </label>
                )}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
                    <div className="p-4 border" style={{ borderColor: 'var(--border)' }}>
                        <div className="text-xs font-mono tracking-widest uppercase text-muted">High Score</div>
                        <div className="font-serif text-3xl mt-1" style={{ color: 'var(--accent)' }}>
                            {highScore}
                        </div>
                    </div>
                    <div className="p-4 border" style={{ borderColor: 'var(--border)' }}>
                        <div className="text-xs font-mono tracking-widest uppercase text-muted">Last Run</div>
                        <div className="text-sm font-mono mt-1" style={{ color: 'var(--ink)' }}>
                            {lastScore ? `${lastScore.score}/${lastScore.total} (${lastScore.accuracy}%)` : 'No runs yet'}
                        </div>
                    </div>
                </div>

                <button onClick={startQuiz} disabled={loadingQuestions} className="btn-primary">
                    {loadingQuestions ? 'Loading Bird Photos...' : 'Start Quiz'}
                </button>
            </div>
        );
    }

    if (phase === 'finished') {
        return (
            <div
                className="p-6 sm:p-8 border max-w-3xl mx-auto"
                style={{ borderColor: 'var(--border)', borderWidth: '1px', backgroundColor: 'var(--card)' }}
            >
                <h2 className="font-serif text-3xl font-bold mb-4" style={{ color: 'var(--ink)' }}>
                    Quiz Complete
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
                    <div className="p-4 border" style={{ borderColor: 'var(--border)' }}>
                        <div className="text-xs font-mono tracking-widest uppercase text-muted">Score</div>
                        <div className="font-serif text-3xl mt-1" style={{ color: 'var(--accent)' }}>
                            {score}/{questions.length}
                        </div>
                    </div>
                    <div className="p-4 border" style={{ borderColor: 'var(--border)' }}>
                        <div className="text-xs font-mono tracking-widest uppercase text-muted">Accuracy</div>
                        <div className="font-serif text-3xl mt-1" style={{ color: 'var(--ink)' }}>
                            {accuracy}%
                        </div>
                    </div>
                    <div className="p-4 border" style={{ borderColor: 'var(--border)' }}>
                        <div className="text-xs font-mono tracking-widest uppercase text-muted">High Score</div>
                        <div className="font-serif text-3xl mt-1" style={{ color: 'var(--accent2)' }}>
                            {Math.max(highScore, score)}
                        </div>
                    </div>
                </div>

                <div className="flex flex-wrap gap-3">
                    <button onClick={startQuiz} className="btn-primary">
                        Play Again
                    </button>
                    <button onClick={restartQuiz} className="btn-outline">
                        Change Settings
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto space-y-5">
            <div
                className="p-4 sm:p-5 border flex flex-wrap items-center gap-4 justify-between"
                style={{ borderColor: 'var(--border)', borderWidth: '1px', backgroundColor: 'var(--card)' }}
            >
                <div className="flex items-center gap-4">
                    <div className="text-xs font-mono tracking-widest uppercase text-muted">
                        Question {questionIndex + 1}/{questions.length}
                    </div>
                    <div className="text-xs font-mono tracking-widest uppercase text-muted">Score {score}</div>
                </div>
                {timedMode && (
                    <div className="text-sm font-mono" style={{ color: timeLeft <= 5 ? 'var(--danger)' : 'var(--ink)' }}>
                        {timeLeft}s left
                    </div>
                )}
            </div>

            <div className="card-border bg-card overflow-hidden">
                {currentQuestion?.imageUrl ? (
                    <div className="w-full flex items-center justify-center" style={{ minHeight: '340px', maxHeight: '430px', backgroundColor: '#efeadf' }}>
                        <img
                            src={currentQuestion.imageUrl}
                            alt="Bird quiz question"
                            className="w-full h-full object-contain"
                            style={{ maxHeight: '430px' }}
                        />
                    </div>
                ) : (
                    <div className="w-full h-72 flex items-center justify-center" style={{ backgroundColor: '#efeadf' }}>
                        <span className="font-mono text-sm text-muted">No photo found for this bird. Guess anyway.</span>
                    </div>
                )}
                <div className="px-4 py-3 text-xs font-mono text-muted border-t" style={{ borderColor: 'var(--border)' }}>
                    Source:{' '}
                    <a href={currentQuestion?.sourceUrl} target="_blank" rel="noreferrer" className="underline hover:text-ink">
                        {currentQuestion?.sourceName || 'Wikipedia'}
                    </a>
                </div>
            </div>

            <div className="p-5 sm:p-6 border bg-card" style={{ borderColor: 'var(--border)', borderWidth: '1px' }}>
                <label className="block text-xs font-mono tracking-widest uppercase text-muted mb-2">Your Guess</label>
                <input
                    type="text"
                    value={guess}
                    onChange={(e) => setGuess(e.target.value)}
                    disabled={answered}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                            e.preventDefault();
                            if (!answered) submitAnswer();
                        }
                    }}
                    placeholder="Type common name (e.g., Collared Kingfisher)"
                    className="w-full px-4 py-3 border bg-card font-mono text-sm"
                    style={{ borderColor: 'var(--border)' }}
                />

                <div className="mt-4 flex flex-wrap items-center gap-3">
                    {!answered ? (
                        <button onClick={submitAnswer} className="btn-primary" disabled={!guess.trim()}>
                            Submit Guess
                        </button>
                    ) : (
                        <button onClick={nextQuestion} className="btn-primary">
                            {questionIndex + 1 === questions.length ? 'Finish Quiz' : 'Next Question'}
                        </button>
                    )}
                </div>

                {answered && (
                    <div
                        className="mt-4 p-4 border"
                        style={{
                            borderColor: lastCorrect ? 'var(--success)' : 'var(--danger)',
                            backgroundColor: lastCorrect ? '#f4fbf2' : '#fff6f3',
                        }}
                    >
                        <div className="font-mono text-sm" style={{ color: lastCorrect ? 'var(--success)' : 'var(--danger)' }}>
                            {lastCorrect ? 'Correct!' : `Not quite. Answer: ${currentQuestion?.commonName}`}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
