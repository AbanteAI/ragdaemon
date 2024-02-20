import scene from './scene.js';

const addEdge = (edge) => {
    const sourceNode = nodes.find(node => node.id === edge.source);
    const targetNode = nodes.find(node => node.id === edge.target);
    
    if (sourceNode && targetNode) {
        const dir = new THREE.Vector3(targetNode.x - sourceNode.x, targetNode.y - sourceNode.y, targetNode.z - sourceNode.z);
        const length = dir.length() - NODE_RADIUS;
        dir.normalize();
        const arrowHelper = new THREE.ArrowHelper(
            dir, 
            new THREE.Vector3(sourceNode.x, sourceNode.y, sourceNode.z), 
            length, 
            "white", 
            SCALE / 5, 
            SCALE / 5,
        );
        arrowHelper.userData = {type: "edge", source: edge.source, target: edge.target, selected: false};        
        scene.add(arrowHelper);
        arrowHelper.userData.setSelected = (selected) => {
            arrowHelper.setColor(selected ? "lime" : "white");
        }
    }
}

export default addEdge;
