import scene from './scene.js';

const addLink = (link) => {
    const sourceNode = nodes.find(node => node.id === link.source);
    const targetNode = nodes.find(node => node.id === link.target);
    
    if (sourceNode && targetNode) {
        const dir = new THREE.Vector3(targetNode.x - sourceNode.x, targetNode.y - sourceNode.y, targetNode.z - sourceNode.z);
        const length = dir.length() - NODE_RADIUS;
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
}

export default addLink;
