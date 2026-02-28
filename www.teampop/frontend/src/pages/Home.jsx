import React from 'react';
import { Link } from 'react-router-dom';
import '../App.css'; 

const Home = () => {
    return (
        <div className="home-container">
            <div className="hero-section">
                <h1>Train your AI on any website</h1>
                <p className="hero-subtitle">Make your data talk with Team Pop.</p>
                <div className="hero-buttons">
                    <Link to="/get-started" className="btn btn-primary">Get Started</Link>
                    <a href="https://github.com/gautamc-creator/team_pop" target="_blank" rel="noopener noreferrer" className="btn btn-secondary">GitHub</a>
                </div>
            </div>
        </div>
    );
};

export default Home;
