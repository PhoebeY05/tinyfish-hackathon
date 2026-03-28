import { NavLink } from 'react-router-dom';

export default function Hero() {
    return (
        <header className="header-border bg-card px-8 sm:px-10 py-5 flex flex-wrap items-baseline gap-4">
            <NavLink className="font-serif text-2xl font-bold tracking-tighter" to="/">
                Avian<span className="italic text-accent">IQ</span>
            </NavLink>
            <div className="text-xs tracking-widest uppercase text-muted border-l border-border pl-4">
                Ornithology Lab
            </div>
            <nav className="ml-auto flex items-center gap-2 sm:gap-3">
                <NavLink
                    to="/"
                    className={({ isActive }) =>
                        `text-xs font-mono tracking-widest uppercase px-3 py-1 border rounded-sm transition ${isActive ? 'bg-ink text-paper border-ink' : 'bg-transparent text-ink border-border hover:border-ink'
                        }`
                    }
                >
                    Analyzer
                </NavLink>
                <NavLink
                    to="/quiz"
                    className={({ isActive }) =>
                        `text-xs font-mono tracking-widest uppercase px-3 py-1 border rounded-sm transition ${isActive ? 'bg-ink text-paper border-ink' : 'bg-transparent text-ink border-border hover:border-ink'
                        }`
                    }
                >
                    Quiz
                </NavLink>
            </nav>
        </header>
    );
}
