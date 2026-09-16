import { axios } from "@/services/axios";

const Uploads = {
  query: (dataSourceId) => axios.get(`api/data_sources/${dataSourceId}/uploads`),
  upload: (dataSourceId, file, name, onUploadProgress) => {
    const formData = new FormData();
    formData.append("file", file);
    if (name) {
      formData.append("name", name);
    }
    return axios.post(`api/data_sources/${dataSourceId}/uploads`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress,
    });
  },
  delete: (dataSourceId, uploadId) => axios.delete(`api/data_sources/${dataSourceId}/uploads/${uploadId}`),
};

export default Uploads;
