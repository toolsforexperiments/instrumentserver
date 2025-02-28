# How to use the dashboard

## Table of Contents
- [File Descriptions](#file-descriptions)
- [Configuring the Dashboard](#configuring-the-dashboard)
- [Starting the Dashboard](#starting-the-dashboard)
- [Extra Notes](#extra-notes)

## File Descriptions
### Provisioning (Folder)
- This folder contains the code to make sure the datasource is already created when the grafana server is launched to reduce necessary configuration
- It is read when [creating the custom grafana Docker image](#creating-the-custom-grafana-docker-image)
- The field "url" in 'csvdatasource.yml' must be modified to [match the directory](#mounting-the-data) of the mounted volume for the datasource in docker-compose.yml. It must also direct to the correct file within the directory
### dashboard.json
- This file is not run nor read by any program. It is provided for the user to be able to [import into grafana](#configuration-within-grafana). It contains the necessary data transformations to visualize the CSV datasource.
### docker-compose.yml
- Use this file to [start the grafana server](#starting-the-dashboard) once you have [created the custom grafana image](#creating-the-custom-grafana-docker-image)
- It contains fields on [setting admin username](#setting-admin-username-and-password), [setting mount location of csv data](#mounting-the-data), [name of the custom image](#creating-the-custom-grafana-docker-image), [location of the admin password](#setting-admin-username-and-password), and extra [environment variable](#environment-variables) configurations as necessary
### Dockerfile
- Used to create the custom Docker image for Grafana
- It creates fields for which [plugins](#plugins) to use, allows for [enviroment variable](#environment-variables) overrrides, and requires the file [grafana.ini](#grafanaini)
### grafana_password.txt
- Write the desired admin password in this file in plaintext
- Is used by [docker-compose.yml](#docker-composeyml)
### grafana.ini
- Is required for the [Dockerfile](#dockerfile) to be used to [create the custom grafana image]

## Configuring the Dashboard
### Mounting the data
- Locate the directory of the data you wish to visualize and replace the first half (before the ':') of the last volume in [docker-compose.yml](#docker-composeyml) with the folder containing the data
- Make sure the second half of the volume matches the path in 'url' in [provisioning/datasources/csvlistener.yml](#provisioning-folder)
### Setting admin username and password
- The admin username is set in [docker-compose.yml](#docker-composeyml). Under 'environment', set  GF_SECURITY_ADMIN_USER to whatever your desired admin username is
- The admin password is set in plaintext in [grafana_password.txt](#grafana_passwordtxt)
### Choosing a port
- In [docker-compose.yml](#docker-composeyml), you can replace which port you would like to host the server at by modifying the first port (before the ':') under 'ports'. This will reflect where the server is being hosted and through which port it can be accessed.
### Environment variables
- Grafana provides supoort for overriding environment variables in order to configure the grafana server. This can be done either in the [Dockerfile](#dockerfile) or in [docker-compose.yml](#docker-composeyml) depending on if you would like the custom image to reflect the changes or not.
### Plugins
- Grafana required the use of plugins for certain types of datasources. They are added in the [Dockerfile](#dockerfile)

## Starting the Dashboard
### Creating the custom grafana Docker image
- The first step after each file has been configured is to create the custom image
- In the directory containing the Dockerfile and grafana.ini, run 'sudo docker build -t (insert-image-name) .'
- Note: There is a '.' at the end of the command
- Replace (insert-image-name) with your desired custom image name
- Update the 'image' field in [docker-compose.yml](#docker-composeyml) to reflect your image name
### Using Docker Compose
- Once you have created the Grafana Image and have finished configuring [docker-compose.yml](#docker-composeyml), in the same directory, run 'sudo docker compose up -d'
- The grafana server should now be accessible using your IP address and port "http://(IP ADDRESS):(PORT)"
- A login screen should appear, use your chosen [admin username and password](#setting-admin-username-and-password)
### Configuration within Grafana
- Once you have opened Grafana, the datasource should already be created under "Connections/Datasources"
- You can test the data imported correctly by opening the datasource under the explore view
- Navigate to the Dashboards window, create a new dashboard, and import [dashboard.json](#dashboardjson)
- The dashboard should now be working

## Extra notes
- If you wish to change the password after already having run the container, you must run the following command: 'sudo docker volume rm docker_grafana-storage'
- Grafana stores the username and password data on the first execution and overwriting environment variables will not change them afterward, so they must be cleared first