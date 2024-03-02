import scene from './three/scene.js';

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

const startControlPanel = () => {
    const searchInput = document.getElementById('search-input');
    const searchResults = document.getElementById('search-results');

    searchInput.addEventListener('keyup', debounce(async (e) => {
        const query = e.target.value;
        if (query.length < 3) { // Clear results if search box is empty
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
    }, 300)); // Adding debounce time of 300 milliseconds
}

export default startControlPanel;
