console.log("nodes: ", nodes);
console.log("links: ", links);
console.log("metadata: ", metadata)

// Scene setup
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
const renderer = new THREE.WebGLRenderer();
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// Initialize OrbitControls
const controls = new THREE.OrbitControls(camera, renderer.domElement);
camera.position.y = 2;
camera.position.z = 5;

// Render nodes based on coordinates
node_radius = 0.05
nodes.forEach(node => {
    const geometry = new THREE.SphereGeometry(node_radius, 32, 32);
    const material = new THREE.MeshBasicMaterial({ color: "white" });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(node.x, node.y, node.z);
    scene.add(sphere);
});
// Render links as arrows
links.forEach(link => {
    const sourceNode = nodes.find(node => node.id === link.source);
    const targetNode = nodes.find(node => node.id === link.target);

    if (sourceNode && targetNode) {
        const dir = new THREE.Vector3(targetNode.x - sourceNode.x, targetNode.y - sourceNode.y, targetNode.z - sourceNode.z);
        const length = dir.length() - node_radius;
        dir.normalize();
        const arrowHelper = new THREE.ArrowHelper(dir, new THREE.Vector3(sourceNode.x, sourceNode.y, sourceNode.z), length, "lime", 0.1, 0.05);
        scene.add(arrowHelper);
    }
});

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
