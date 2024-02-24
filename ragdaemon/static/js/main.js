import scene from './three/scene.js';
import camera from './three/camera.js';
import renderer from './three/renderer.js';
import controls from './three/controls.js';
import raycaster from './three/raycaster.js';
import addNode from './three/node.js';
import addEdge from './three/edge.js';

import startControlPanel from './controlPanel.js';

/*

Global variables
================
nodes       array[object]
edges       array[object]
metadata    object
SCALE       float
NODE_RADIUS float
*/


const initialize = () => {
    // Load the graph
    nodes.forEach(node => {
        if (node.layout?.hierarchy) {
            addNode(node);
        } else {
            console.error(`Node ${node.id} does not have a hierarchy layout`);
        }
    })
    edges.forEach(edge => {
        addEdge(edge);
    })
    // Select root node (highest y)
    const rootNode = nodes.reduce((acc, node) => node.y > acc.y ? node : acc);
    const rootSphere = scene.children.find(child => child.userData.id === rootNode.id);
    rootSphere.userData.handleClick();
    // Main animation loop
    function animate() {
        requestAnimationFrame(animate);
        renderer.render(scene, camera);
        controls.update();
    }
    animate();
    
    // Handle window resize
    const sceneContainer = document.getElementById('scene-container');
    const resize = () => {
        camera.aspect = sceneContainer.clientWidth / sceneContainer.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(sceneContainer.clientWidth, sceneContainer.clientHeight);
    }
    window.addEventListener('resize', resize);
    resize();

    startControlPanel();
}
initialize();
