import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/Header.css'; // Assume basic styles or inline them for now

const Header = () => {
    return (
        <header className="app-header">
            <div className="header-left">
                <Link to="/" className="logo">Team Pop</Link>
            </div>
            <nav className="header-right">
                <Link to="/docs">Docs</Link>
                <a href="https://github.com/gautamc-creator/team_pop" target="_blank" rel="noopener noreferrer">GitHub</a>
                <Link to="/get-started" className="btn-header">Get Started</Link>
            </nav>
        </header>
    );
};

export default Header;
