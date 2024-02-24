import scene from './scene.js';

const addEdge = (edge) => {
    const sourceNode = nodes.find(node => node.id === edge.source);
    const targetNode = nodes.find(node => node.id === edge.target);
    
    if (sourceNode && targetNode) {
        const sourcePos = sourceNode.layout?.hierarchy;
        const targetPos = targetNode.layout?.hierarchy;
        const dir = new THREE.Vector3(targetPos.x - sourcePos.x, targetPos.y - sourcePos.y, targetPos.z - sourcePos.z);
        const length = dir.length() - NODE_RADIUS;
        dir.normalize();
        const arrowHelper = new THREE.ArrowHelper(
            dir, 
            new THREE.Vector3(sourcePos.x, sourcePos.y, sourcePos.z), 
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
