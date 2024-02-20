import scene from './three/scene.js';

const startControlPanel = () => {
    const controlPanel = document.getElementById('control-panel');
    const selectableItems = scene.children.filter(child => child.userData.setSelected)

    // Header
    const header = document.getElementById('header');
    header.innerText = "ragdaemon"
    header.style.textAlign = "center"
    header.style.fontFamily = "Courier New"

    const buttonContainer = document.getElementById('button-container');
    const selectedNodeDisplay = document.getElementById('selected-node-display');

    const allButton = document.createElement('button');
    buttonContainer.appendChild(allButton);
    allButton.innerHTML = 'select all';
    allButton.style.width = '45%';
    allButton.style.height = '50px';
    allButton.addEventListener('click', () => {
        selectableItems.forEach(item => item.userData.setSelected(true))
        selectedNodeDisplay.innerHTML = ""
    });

    const noneButton = document.createElement('button');
    buttonContainer.appendChild(noneButton);
    noneButton.innerHTML = 'select none';
    noneButton.style.width = '45%';
    noneButton.style.height = '50px';
    noneButton.addEventListener('click', () => {
        selectableItems.forEach(item => item.userData.setSelected(false))
        selectedNodeDisplay.style.display = "none"
    });
}

export default startControlPanel;
