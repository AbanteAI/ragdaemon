import scene from './scene.js';

function create3DTextLabel(sphere) {
    const id = sphere.userData.id;
    const position = sphere.position;
    const loader = new THREE.FontLoader();
    const font_url = 'https://threejs.org/examples/fonts/helvetiker_regular.typeface.json';
    // Load a font
    loader.load(font_url, font => {
        const textGeometry = new THREE.TextGeometry(id, {
            font: font,
            size: SCALE / 5,
            height: 0,
            curveSegments: 12,
            bevelEnabled: false,
        });
        const textMaterial = new THREE.MeshBasicMaterial({ color: "white" });
        const textMesh = new THREE.Mesh(textGeometry, textMaterial);
        textMesh.position.set(position.x, position.y + (2 * NODE_RADIUS), position.z); // Centered horizontally and twice as close
        textMesh.geometry.center(); // Center the text geometry
        textMesh.visible = false;
        scene.add(textMesh);
        sphere.userData.setSelected = (selected) => {
            textMesh.visible = selected;
            sphere.material.color.set(selected ? "lime" : "white");
        }
        sphere.userData.handleClick = () => {
            const selected = !textMesh.visible;
            const nodesToUpdate = new Set();
            nodesToUpdate.add(id);
            const edges = scene.children.filter(child => child.userData.type === "edge");
            edges.forEach(edge => {
                if (edge.userData.source === id || edge.userData.target === id) {
                    edge.userData.setSelected(selected);
                    nodesToUpdate.add(edge.userData.source);
                    nodesToUpdate.add(edge.userData.target);
                }
            })
            const nodes = scene.children.filter(child => child.userData.type === "node");
            nodes.forEach(node => {
                if (nodesToUpdate.has(node.userData.id)) {
                    node.userData.setSelected(selected);
                }
            })
        }
    });
}

const addNode = (node) => {
    const geometry = new THREE.SphereGeometry(NODE_RADIUS, 32, 32);
    const material = new THREE.MeshBasicMaterial({ color: "white" });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(node.x, node.y, node.z);
    sphere.userData = {type: "node", id: node.id};
    scene.add(sphere);
    
    create3DTextLabel(sphere);
}

export default addNode;
