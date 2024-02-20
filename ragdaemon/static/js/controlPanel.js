import scene from './three/scene.js';

const startControlPanel = () => {
    const controlPanel = document.getElementById('control-panel');
    const selectableItems = scene.children.filter(child => child.userData.setSelected)

    // Header
    const header = document.createElement('h1')
    header.innerText = "ragdaemon"
    header.style.textAlign = "center"
    header.style.fontFamily = "Courier New"
    controlPanel.appendChild(header);

    // Buttons
    const buttonContainer = document.createElement('div');
    buttonContainer.style.width = '100%';
    buttonContainer.style.display = 'flex';
    buttonContainer.style.justifyContent = 'space-around';
    controlPanel.appendChild(buttonContainer);

    const allButton = document.createElement('button');
    allButton.innerHTML = 'select all';
    allButton.style.width = '45%';
    allButton.style.height = '50px';
    allButton.addEventListener('click', () => {
        selectableItems.forEach(item => item.userData.setSelected(true))
    });

    const noneButton = document.createElement('button');
    noneButton.innerHTML = 'select none';
    noneButton.style.width = '45%';
    noneButton.style.height = '50px';
    noneButton.addEventListener('click', () => {
        selectableItems.forEach(item => item.userData.setSelected(false))
    });

    buttonContainer.appendChild(allButton);
    buttonContainer.appendChild(noneButton);

}

export default startControlPanel;
