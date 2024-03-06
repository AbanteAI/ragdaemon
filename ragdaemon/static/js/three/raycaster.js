import scene from './scene.js';
import camera from './camera.js';

// Raycaster for mouse interaction
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
raycaster.far = camera.far * 10; // Set the raycaster's maximum distance to the camera's far plane

const container = document.getElementById('scene-container');
function getClickTarget(event, dblclick=false) {
    // Calculate mouse position in normalized device coordinates
    // (-1 to +1) for both components
    mouse.x = (event.clientX / container.clientWidth) * 2 - 1;
    mouse.y = - (event.clientY / container.clientHeight) * 2 + 1;

    // Update the picking ray with the camera and mouse position
    raycaster.setFromCamera(mouse, camera);

    // Calculate objects intersecting the picking ray
    // Filter objects by those that have a toggleSelected method
    const clickables = dblclick
        ? scene.children.filter(child => child.userData.handleDoubleClick)
        : scene.children.filter(child => child.userData.handleClick);
    const intersects = raycaster.intersectObjects(clickables)
    if (intersects.length === 0) {
        return null;
    }
    return intersects[0].object;
}

// Add event listener for mouse clicks
window.addEventListener('click', (event) => {
    const target = getClickTarget(event);
    if (target) {
        target.userData.handleClick(event);
    }
}, false)

window.addEventListener('dblclick', (event) => {
    const target = getClickTarget(event);
    if (target) {
        target.userData.handleDoubleClick(event);
    }
}, false)

export default raycaster;
