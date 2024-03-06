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
let cameraTargetPosition = null;
let cameraTargetLookAt = null;

function lookAtSelectedNodes(selectedNodes) {
    // Move the camera to fit all selected nodes in frame
    const bbox = new THREE.Box3();
    selectedNodes.forEach(sphere => {
        bbox.expandByObject(sphere);
    });

    const center = bbox.getCenter(new THREE.Vector3());
    const size = bbox.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);
    const fov = 45;
    const cameraDistance = maxDim / 2 / Math.tan(THREE.MathUtils.degToRad(fov / 2));
    cameraTargetPosition = new THREE.Vector3(center.x, center.y, center.z + cameraDistance);
    cameraTargetLookAt = center;
}

const getNeighbors = (nodeId) => {
    const neighbors = new Set();
    edges.forEach(edge => {
        if (edge.source === nodeId) {
            neighbors.add(edge.target);
        } else if (edge.target === nodeId) {
            neighbors.add(edge.source);
        }
    })
    return neighbors;
}

const initialize = () => {
    // Load the graph
    nodes.forEach(node => {
        if (node.layout?.hierarchy) {
            addNode(node, lookAtSelectedNodes, getNeighbors);
        } else {
            console.error(`Node ${node.id} does not have a hierarchy layout`);
        }
    })
    edges.forEach(edge => {
        addEdge(edge);
    })
    // Select root node (highest y)
    const rootNode = nodes.filter(node => node.id === "ROOT")[0];
    const rootSphere = scene.children.find(child => child.userData.id === rootNode.id);
    rootSphere.userData.handleClick();
    // Main animation loop
    function animate() {
        requestAnimationFrame(animate);
        renderer.render(scene, camera);
        controls.update();
        // Camera movement
        if (cameraTargetPosition && cameraTargetLookAt) {
            const step = 0.05;
            camera.position.lerp(cameraTargetPosition, step);
            controls.target.lerp(cameraTargetLookAt, step);

            if (camera.position.distanceTo(cameraTargetPosition) < 0.1) {
                cameraTargetPosition = null; // Stop moving the camera
                cameraTargetLookAt = null;
            }
        }
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
