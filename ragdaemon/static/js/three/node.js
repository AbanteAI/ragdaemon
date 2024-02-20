import scene from './scene.js';

function create3DTextLabel(text, position) {
    const loader = new THREE.FontLoader();
    const font_url = 'https://threejs.org/examples/fonts/helvetiker_regular.typeface.json';
    // Load a font
    loader.load(font_url, font => {
        const textGeometry = new THREE.TextGeometry(text, {
            font: font,
            size: SCALE / 5,
            height: 0,
            curveSegments: 12,
            bevelEnabled: false,
        });
        const textMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff });
        const textMesh = new THREE.Mesh(textGeometry, textMaterial);
        textMesh.position.set(position.x, position.y + (2 * NODE_RADIUS), position.z); // Centered horizontally and twice as close
        textMesh.geometry.center(); // Center the text geometry
        scene.add(textMesh);
    });
}

const addNode = (node) => {
    const geometry = new THREE.SphereGeometry(NODE_RADIUS, 32, 32);
    const material = new THREE.MeshBasicMaterial({ color: "white" });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(node.x, node.y, node.z);
    sphere.userData = {text: node.id};
    scene.add(sphere);
    
    create3DTextLabel(node.id, {x: node.x, y: node.y, z: node.z});
}

export default addNode;
