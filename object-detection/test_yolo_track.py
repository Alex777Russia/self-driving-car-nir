from typing import Any
import torch
import numpy as np
import cv2
from time import perf_counter
from ultralytics import YOLO
from pathlib import Path
from types import SimpleNamespace
import carla
import random
import time

class_id = [2, 3, 5, 7]
class_name = { 2: 'car', 3: 'motobike', 5: 'bus', 7: 'truck'}

img_w = 256 * 4
img_h = 256 * 3
palette = (2 ** 11 - 1, 2 ** 15 - 1, 2 ** 20 - 1)
output_path = "only_yolo_detect.mp4"

class main:

    def __init__(self):
        
        self.model = self.load_model()
        print('after load model')
        self.save_vid = True
        self.output_path = "output.mp4"

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print("CUDA" if torch.cuda.is_available() else "CPU")

        
    def load_model(self):
        model = YOLO('weights/yolov8n.pt')
        return model

    def yolo_details(self, frame):
        results = self.model(frame)
        bbox_xyxy = []
        conf_score = []
        cls_id = []          
        for box in results:
            rows = [row for row in box.boxes.data.tolist() if int(row[5]) in class_id and row[5] != 0]
            bbox_xyxy.extend([[int(x1), int(y1), int(x2), int(y2)] for x1, y1, x2, y2, conf, id in rows])
            conf_score.extend([conf for x1, y1, x2, y2, conf, id in rows])
            cls_id.extend([int(id) for x1, y1, x2, y2, conf, id in rows])
        return frame , bbox_xyxy , conf_score , cls_id    

    def video(self, frame, path, fps, frame_width, frame_height):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video_writer = cv2.VideoWriter(output_path, fourcc, fps, (frame_width, frame_height)) 
        for f in frame:
            video_writer.write(f)
          
    def photo(self, frame, path, idx):
        cv2.imwrite(path+str(idx)+".png", frame)
    

    def __call__(self):
        # The local Host for carla simulator is 2000
        client = carla.Client('localhost', 2000)
        client.set_timeout(20.0)
        world = client.get_world() 

        '''
       climate = carla.WeatherParameters(
                    cloudiness=50.0,
                    precipitation=90.0,
                    sun_altitude_angle=70.0,
                    wetness = 50.0,
                    fog_density = 50.0)
        
        world.set_weather(climate)
        '''

        spawn_points = world.get_map().get_spawn_points()
        vehicle_bp = world.get_blueprint_library().find('vehicle.lincoln.mkz_2020')
        vehicle_bp.set_attribute('role_name', 'ego')
        ego_vehicle = world.try_spawn_actor(vehicle_bp, random.choice(spawn_points))

        spectator = world.get_spectator()
        transform = carla.Transform(ego_vehicle.get_transform().transform(carla.Location(x=-4, z=2.5)), carla.Rotation()) # Rotation yaw=-180, pitch=-90
        spectator.set_transform(transform)

        for i in range(60):
            vehicle_bp = random.choice(world.get_blueprint_library().filter('vehicle'))
            npc = world.try_spawn_actor(vehicle_bp, random.choice(spawn_points))
            
        if npc:
            for v in world.get_actors().filter('*vehicle*'):
                v.set_autopilot(True)
                   
        camera_bp = world.get_blueprint_library().find('sensor.camera.rgb')
        camera_bp.set_attribute('image_size_x', f'{img_w}')
        camera_bp.set_attribute('image_size_y', f'{img_h}')
        camera_bp.set_attribute('fov', '110')
        
        camera_location = carla.Location(2,0,1)
        camera_rotation = carla.Rotation(0,180,0)

        camera_init_trans = carla.Transform(camera_location,camera_rotation)
        camera = world.spawn_actor(camera_bp, camera_init_trans, attach_to=ego_vehicle , attachment_type=carla.AttachmentType.SpringArmGhost)
        
        def capture_image(image):
            image_data = np.array(image.raw_data)
            image_rgb = image_data.reshape((image.height, image.width, 4))[:, :, :3]
            return image_rgb

        image_w = camera_bp.get_attribute('image_size_x').as_int()
        image_h = camera_bp.get_attribute('image_size_y').as_int()

        camera_data = {'image': np.zeros((image_h, image_w, 4))}
        camera.listen(lambda image: camera_data.update({'image': capture_image(image)}))
        
        ego_vehicle.set_autopilot(True)

        # TODO: расскоментить если необходимо смотреть ещё и путь (рисуется за движущимся объектом)
        # from collections import defaultdict
        # track_history = defaultdict(lambda: [])

        try:
            while True:
                frame = camera_data['image']
                # frame , bbox_xyxy , conf_score , cls_id = self.yolo_details(frame)              
                # # outputs = self.deepsort.update(bbox_xyxy, conf_score, frame)
                # frame = self.draw_bbox(frame, bbox_xyxy, conf_score, cls_id)


                results = self.model.track(frame, persist=True)

                # if results[0].boxes.id != None:
                #     boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
                #     track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                # else:
                #     boxes = []
                #     track_ids = []

                annotated_frame = results[0].plot()

                # for box, track_id in zip(boxes, track_ids):
                #     x, y, w, h = box
                #     track = track_history[track_id]
                #     track.append((float(x), float(y)))  # x, y center point
                #     if len(track) > 30:  # retain 90 tracks for 90 frames
                #         track.pop(0)
                #     # Draw the tracking lines
                #     points = np.hstack(track).astype(np.int32).reshape((-1, 1, 2))
                #     cv2.polylines(annotated_frame, [points], isClosed=False, color=(230, 230, 230), thickness=10)

                frame = cv2.UMat(annotated_frame)
                cv2.imshow('YOLO.track', frame)

                if cv2.waitKey(1) == ord('q'):
                    break 
        finally:
            self.destroy_world(camera, ego_vehicle, world)
            print('all actors destroyed')
     
    def destroy_world(self,camera , vehicle ,world):
        cv2.destroyAllWindows()
        camera.stop()
        camera.destroy()
        vehicle.destroy()
        for npc in world.get_actors().filter('vehicle*'):
            if npc:
                npc.destroy()

    def colour_label(self , label):
        label_colour = [int((p * (label ** 2 - label + 1)) % 255) for p in palette]
        return tuple(label_colour)    
    
    def draw_bbox(self, frame, output, conf, cls_id):
        print(f"output: {output}")
        print(f"cls_id: {cls_id}")
        if not output:
            frame = np.array(frame)
            return frame
        else:
            for i in range(len(output)):
                x1, y1, x2, y2 = int(output[i][0]), int(output[i][1]), int(output[i][2]), int(output[i][3])
                label = class_name.get(cls_id[i], '')
                frame = np.array(frame)
                colour = self.colour_label(cls_id[i])
                t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_PLAIN, 1 , 1)[0]
                c_id = f'{label}'
                cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 1)
                cv2.rectangle(frame, (x1, y1), (x1 + t_size[0] + 3, y1 + t_size[1] + 4), colour, -1)
                cv2.putText(frame, c_id, (x1, y1 + t_size[1] + 4), cv2.FONT_HERSHEY_PLAIN, 1, [255, 255, 255], 2)

        return frame
    
if __name__ == '__main__':
    run = main()