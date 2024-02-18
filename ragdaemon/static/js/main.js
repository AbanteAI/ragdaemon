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
controls.target.set(0, 0.7, 0);
camera.position.set(0, 0.7, 2.5);

// Render nodes based on coordinates
SCALE = Math.sqrt(1 / nodes.length);
node_radius = SCALE / 5
nodes.forEach(node => {
    const geometry = new THREE.SphereGeometry(node_radius, 32, 32);
    const material = new THREE.MeshBasicMaterial({ color: "white" });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(node.x, node.y, node.z);
    scene.add(sphere);
    
    // Function to create a 3D text label
    function create3DTextLabel(text, position) {
        const loader = new THREE.FontLoader();
        font_url = 'https://threejs.org/examples/fonts/helvetiker_regular.typeface.json';
        // Load a font
        loader.load(font_url, font => {
            const textGeometry = new THREE.TextGeometry(text, {
                font: font,
                size: SCALE / 5, // Reduced size by 50%
                height: SCALE / 10,
                curveSegments: 12,
                bevelEnabled: false,
            });
            const textMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff });
            const textMesh = new THREE.Mesh(textGeometry, textMaterial);
            textMesh.position.set(position.x, position.y + (2 * node_radius), position.z); // Centered horizontally and twice as close
            textMesh.geometry.center(); // Center the text geometry
            scene.add(textMesh);
        });
    }
    create3DTextLabel(node.id, {x: node.x, y: node.y, z: node.z});
});
// Render links as arrows
links.forEach(link => {
    const sourceNode = nodes.find(node => node.id === link.source);
    const targetNode = nodes.find(node => node.id === link.target);

    if (sourceNode && targetNode) {
        const dir = new THREE.Vector3(targetNode.x - sourceNode.x, targetNode.y - sourceNode.y, targetNode.z - sourceNode.z);
        const length = dir.length() - node_radius;
        dir.normalize();
        const arrowHelper = new THREE.ArrowHelper(
            dir, 
            new THREE.Vector3(sourceNode.x, sourceNode.y, sourceNode.z), 
            length, 
            "lime", 
            SCALE / 5, 
            SCALE / 5,
        );
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
