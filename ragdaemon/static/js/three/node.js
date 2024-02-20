import scene from './scene.js';

function createCanvasTexture(text) {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    canvas.width = 1024; // Super-wide to accomodate long names
    canvas.height = 64; // Set height for the texture
    context.font = 'Bold 20px Arial';
    context.fillStyle = 'white';
    context.textAlign = 'center';
    context.fillText(text, canvas.width / 2, canvas.height / 2);
    const texture = new THREE.Texture(canvas);
    texture.needsUpdate = true;
    texture.minFilter = THREE.LinearFilter; // This will prevent texture filtering from blurring the text
    return texture;
}

const addNode = (node) => {
    // Sphere
    const geometry = new THREE.SphereGeometry(NODE_RADIUS, 32, 32);
    const material = new THREE.MeshBasicMaterial({ color: "lightgray" });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.set(node.x, node.y, node.z);
    sphere.userData = {type: "node", id: node.id};
    scene.add(sphere);
    
    // Label
    const id = sphere.userData.id;
    const position = sphere.position;
    const canvasTexture = createCanvasTexture(id);
    const spriteMaterial = new THREE.SpriteMaterial({ map: canvasTexture });
    const sprite = new THREE.Sprite(spriteMaterial);
    sprite.position.set(position.x, position.y + (2 * NODE_RADIUS), position.z);
    sprite.scale.set(2, 0.125, 1); // Scale the sprite to an appropriate size
    sprite.visible = false;
    scene.add(sprite);

    // Methods
    sphere.userData.setSelected = (selected) => {
        sprite.visible = selected;
        sphere.material.color.set(selected ? "lime" : "lightgray");
    };
    sphere.userData.handleClick = () => {
        const selected = !sprite.visible;
        const nodesToUpdate = new Set();
        nodesToUpdate.add(id);
        const edges = scene.children.filter(child => child.userData.type === "edge");
        edges.forEach(edge => {
            if (edge.userData.source === id || edge.userData.target === id) {
                edge.userData.setSelected(selected);
                nodesToUpdate.add(edge.userData.source);
                nodesToUpdate.add(edge.userData.target);
            }
        });
        const nodes = scene.children.filter(child => child.userData.type === "node");
        nodes.forEach(node => {
            if (nodesToUpdate.has(node.userData.id)) {
                node.userData.setSelected(selected);
            }
        });
    };
}

export default addNode;
