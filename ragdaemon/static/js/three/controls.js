import camera from './camera.js';
import renderer from './renderer.js';

const container = document.getElementById('scene-container');
const controls = new THREE.OrbitControls(camera, container);

controls.target.set(0, 0.7, 0);

export default controls;
