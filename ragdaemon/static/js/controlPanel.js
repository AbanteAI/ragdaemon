import scene from './three/scene.js';

const startControlPanel = () => {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');

    searchInput.addEventListener('keyup', async (e) => {
        if (e.key === 'Enter') {
            const query = e.target.value;
            if (query.length < 3) { // Minimum query length
                searchResults.innerHTML = '';
                return;
            }
            const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
            const results = await response.json();
            searchResults.innerHTML = ''; // Clear previous results
            results.forEach(result => {
                const resultPanel = document.createElement('div');
                resultPanel.className = 'result-panel';
                resultPanel.textContent = result;
                searchResults.appendChild(resultPanel);
            });
        }
    });
}

export default startControlPanel;
