import scene from './scene.js';
import camera from './camera.js';

// Raycaster for mouse interaction
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
raycaster.far = camera.far * 10; // Set the raycaster's maximum distance to the camera's far plane

function onMouseClick(event) {
    // Calculate mouse position in normalized device coordinates
    // (-1 to +1) for both components
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = - (event.clientY / window.innerHeight) * 2 + 1;

    // Update the picking ray with the camera and mouse position
    raycaster.setFromCamera(mouse, camera);

    // Calculate objects intersecting the picking ray
    const clickables = scene.children.filter(child => child.userData && child.userData.text);
    const intersects = raycaster.intersectObjects(clickables)
    for (let i = 0; i < intersects.length; i++) {
        console.log(intersects[i].object.userData.text);
        break; // Assuming we only want to log the first object that was clicked
    }
}

// Add event listener for mouse clicks
window.addEventListener('click', onMouseClick, false);

export default raycaster;
