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

const addNode = (node, onClickCallback, getNeighbors) => {
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
    sphere.userData.handleClick = (event) => {
        // Select hierarchy parent recursively until root (no parent)
        const edges = scene.children.filter(child => child.userData.type === "edge");
        const nodes = scene.children.filter(child => child.userData.type === "node");
        const selected = !sprite.visible;
        if (!event?.shiftKey) {
            edges.forEach(edge => edge.userData.setSelected(false));
            nodes.forEach(node => node.userData.setSelected(false));
        }
        
        const nodesToUpdate = new Set();
        sphere.userData.setSelected(selected);
        nodesToUpdate.add(sphere);
        const linkToRoot = (node_id, killswitch=20) => {
            if (killswitch == 0) {
                throw new Error("Infinite loop detected");
            }
            const inbound_edge = edges.find(edge => edge.userData.target === node_id);
            if (inbound_edge) {
                inbound_edge.userData.setSelected(selected);
                const parent = inbound_edge.userData.source;
                const parent_node = nodes.find(node => node.userData.id === parent);
                parent_node.userData.setSelected(selected);
                nodesToUpdate.add(parent_node);
                linkToRoot(parent, killswitch-1);
            }
        }
        if (selected || !event?.shiftKey) {
            linkToRoot(id);
        }

        if (selected) {
            onClickCallback(nodesToUpdate);
        }
    };
    sphere.userData.handleDoubleClick = (event) => {
        if (!event?.shiftKey) {
            scene.children.filter(child => child.userData.setSelected).forEach(child => {
                child.userData.setSelected(false);
            });
        }
        const neighborIds = getNeighbors(id);
        neighborIds.add(id);
        const neighbors = scene.children.filter(child => 
            (child.userData.type === "node" && neighborIds.has(child.userData.id)) ||
            (child.userData.type === "edge" && (child.userData.source === id || child.userData.target === id))
        );
        neighbors.forEach(object => {
            object.userData.setSelected(true);
        });
        onClickCallback(neighbors);
    }
}

export default addNode;
