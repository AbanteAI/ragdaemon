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
    const node_pos = node.layout.hierarchy;
    sphere.position.set(node_pos.x, node_pos.y, node_pos.z);
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
            } else {
                edge.userData.setSelected(false);
            }
        });
        const nodes = scene.children.filter(child => child.userData.type === "node");
        nodes.forEach(_node => {
            if (nodesToUpdate.has(_node.userData.id)) {
                _node.userData.setSelected(selected);
            } else {
                _node.userData.setSelected(false);
            }
        });

        // Update controlPanel
        const selectedNodeDisplay = document.getElementById('selected-node-display');
        if (selected) {
            selectedNodeDisplay.style.display = "block";
            const name = node.id.split(/\.|:/).pop();
            selectedNodeDisplay.innerHTML = `<h3>${name}</h3>\n`
            Object.entries(node).forEach(([key, value]) => {
                selectedNodeDisplay.innerHTML += `<li>${key}: ${value}</li>`
            })
        } else {
            selectedNodeDisplay.style.display = "none";
        }
    };
}

export default addNode;
