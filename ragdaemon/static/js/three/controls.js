import camera from './camera.js';
import renderer from './renderer.js';

const controls = new THREE.OrbitControls(camera, renderer.domElement);

controls.target.set(0, 0.7, 0);

export default controls;
