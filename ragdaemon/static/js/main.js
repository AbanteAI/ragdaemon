import scene from './three/scene.js';
import camera from './three/camera.js';
import renderer from './three/renderer.js';
import controls from './three/controls.js';
import raycaster from './three/raycaster.js';
import addNode from './three/node.js';
import addEdge from './three/edge.js';

// Global variables
// console.log("nodes: ", nodes);
// console.log("edges: ", edges);
// console.log("metadata: ", metadata)
// console.log("SCALE: ", SCALE)
// console.log("NODE_RADIUS: ", NODE_RADIUS)

nodes.forEach(node => {
    addNode(node);
})
edges.forEach(edge => {
    addEdge(edge);
})

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
    controls.update();
}
animate();

// Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}, false);

// Initialize with root node (highest y-coordinate) selected
const rootNode = nodes.reduce((acc, node) => node.y > acc.y ? node : acc);
const rootSphere = scene.children.find(child => child.userData.id === rootNode.id);
rootSphere.userData.handleClick();
