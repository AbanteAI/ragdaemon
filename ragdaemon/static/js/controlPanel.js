import scene from './three/scene.js';

const startControlPanel = () => {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');

searchInput.addEventListener('keyup', async (e) => {
    const query = e.target.value;
    if (query.length === 0) { // Clear results if search box is empty
        searchResults.innerHTML = '';
        return;
    }
    if (e.key === 'Enter') {
        if (query.length < 3) { // Minimum query length
            searchResults.innerHTML = '';
            return;
        }
        const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
        searchResults.innerHTML = await response.text();
        document.querySelectorAll('.result-panel').forEach(panel => {
            panel.addEventListener('click', () => {
                const resultId = panel.getAttribute('data-id');
                scene.children.find(child => child.userData.id === resultId).userData.handleClick();
            });
        });
    }
});
}

export default startControlPanel;
